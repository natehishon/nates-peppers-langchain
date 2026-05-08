import os
from typing import TypedDict, Optional
from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, END
from langgraph.types import interrupt  # New import for pausing
from dotenv import load_dotenv
import httpx
import base64
from .database import checkpointer

load_dotenv()

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT")

class ExtractionResult(BaseModel):
    customer_name: str
    pepper_variety: Optional[str] = Field(default=None)
    scoville_rating: Optional[int] = Field(default=None)
    experience_level: Optional[int] = Field(default=None)

class SignatureResult(BaseModel):
    is_signed: bool
    confidence: float


class OrderState(TypedDict):
    pdf_url: str
    pdf_base64: Optional[str]
    extraction: Optional[ExtractionResult]
    signature: Optional[SignatureResult]
    decision: str
    retry_count: int
    hint: str

llm = ChatGoogleGenerativeAI(model="gemini-3.1-flash-lite-preview", project=PROJECT_ID)

def extraction_node(state: OrderState):
    try:
        response = httpx.get(state["pdf_url"], follow_redirects=True, timeout=10.0)

        response.raise_for_status()
        pdf_bytes = response.content
        pdf_b64 = base64.b64encode(pdf_bytes).decode("utf-8")
    except Exception as e:
        return {"hint": f"Download failed: {str(e)}", "retry_count": state["retry_count"] + 1}

    pdf_base64 = base64.b64encode(pdf_bytes).decode("utf-8")

    if state["retry_count"] == 0:
        return {
            "extraction": ExtractionResult(
                customer_name="Nate",
                pepper_variety=None,
                scoville_rating=None,
                experience_level=1
            ),
            "retry_count": 1,
            "hint": "The Scoville SHU was obscured by a digital artifact. Look closer at the table."
        }

    structured_llm = llm.with_structured_output(ExtractionResult)

    base_prompt = "Extract customer name, pepper variety, Scoville SHU, and experience level (1-10)."
    if state["hint"]:
        base_prompt += f"\n\nCRITICAL HINT: {state['hint']}"

    msg = HumanMessage(content=[
        {"type": "text", "text": base_prompt},
        {"type": "media", "mime_type": "application/pdf", "data": pdf_base64}
    ])

    result = structured_llm.invoke([msg])
    return {"extraction": result, "retry_count": state["retry_count"] + 1, "pdf_base64": pdf_b64}


def signature_node(state: OrderState):
    structured_llm = llm.with_structured_output(SignatureResult)

    prompt = """
            Analyze the signature block. 
            A valid signature must look like a deliberate, handwritten name or formalized mark.

            Reject (is_signed=False) if:
            - It is just a single 'squiggly line' or a dot.
            - It looks like a random mark rather than a name.
            - The signature line is blank.

            If it is a 'scribble' that resembles initials but is barely legible, 
            set is_signed=True but set confidence LOW (between 0.1 and 0.4).
            """
    msg = HumanMessage(content=[{"type": "text", "text": prompt},
                                {"type": "media", "mime_type": "application/pdf", "data": state["pdf_base64"]}])

    result = structured_llm.invoke([msg])

    return {"signature": result}


def manual_review_node(state: OrderState):
    choice = interrupt({
        "info": "Manual review required",
        "customer": state["extraction"].customer_name
    })

    if choice.lower() == 'y':
        return {"decision": "APPROVED: Manually cleared by Nate."}
    return {"decision": "REJECTED: Manual review failed or data incomplete."}


def safety_validation_node(state: OrderState):
    ext = state["extraction"]
    sig = state["signature"]

    missing_fields = []
    if not ext.pepper_variety: missing_fields.append("Pepper Name")
    if ext.scoville_rating is None: missing_fields.append("Scoville Rating")
    if ext.experience_level is None: missing_fields.append("Experience Level")

    if missing_fields:
        return {
            "decision": f"REJECTED: Audit incomplete. Missing: {', '.join(missing_fields)}."
        }

    if not sig.is_signed:
        return {"decision": "REJECTED: Liability waiver must be signed."}

    safe_limit = ext.experience_level * 250000
    if ext.scoville_rating > safe_limit:
        return {
            "decision": f"REJECTED: {ext.scoville_rating:,} SHU is too high for your level {ext.experience_level}."
        }

    return {"decision": f"APPROVED: {ext.pepper_variety} verified and safe to ship."}


def extraction_router(state: OrderState):
    is_missing_data = not state["extraction"].pepper_variety or state["extraction"].scoville_rating is None

    if is_missing_data:
        if state["retry_count"] < 3:
            return "retry"
        else:
            print("\n[!] MAX RETRIES REACHED: Still missing data. Escalating to Manual Review.")
            return "manual_review"

    return "verify_signature"

def review_router(state: OrderState):
    if 0.1 < state["signature"].confidence < 0.7:
        return "manual_review"
    return "validate_safety"


workflow = StateGraph(OrderState)

workflow.add_node("extract_data", extraction_node)
workflow.add_node("verify_signature", signature_node)
workflow.add_node("validate_safety", safety_validation_node)
workflow.add_node("manual_review", manual_review_node)

workflow.set_entry_point("extract_data")

workflow.add_conditional_edges("extract_data", extraction_router, {
    "retry": "extract_data", "verify_signature": "verify_signature", "manual_review": "manual_review"
})

workflow.add_conditional_edges("verify_signature", review_router, {
    "manual_review": "manual_review", "validate_safety": "validate_safety"
})

workflow.add_edge("manual_review", END)
workflow.add_edge("validate_safety", END)

graph = workflow.compile(checkpointer=checkpointer)
