import base64
import os
from dotenv import load_dotenv
from typing import TypedDict, Optional
from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, END

load_dotenv()

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT")

llm = ChatGoogleGenerativeAI(model="gemini-3.1-flash-lite-preview",
                                 project=PROJECT_ID)

class ExtractionResult(BaseModel):
    customer_name: str
    pepper_variety: Optional[str] = Field(default=None)
    scoville_rating: Optional[int] = Field(default=None)
    experience_level: Optional[int] = Field(default=None, description="Experience 1-10")


class SignatureResult(BaseModel):
    is_signed: bool
    confidence: float = Field(description="0-1 certainty of handwritten signature")


class OrderState(TypedDict):
    pdf_base64: str
    extraction: Optional[ExtractionResult]
    signature: Optional[SignatureResult]
    decision: str
    retry_count: int
    hint: str


def extraction_node(state: OrderState):
    if state["retry_count"] == 0:
        print("\n[DEMO] Step 1: Simulating a failed/blurry extraction...")
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

    print(f"\n[DEMO] Step 2: Retrying with Hint: {state['hint']}")

    structured_llm = llm.with_structured_output(ExtractionResult)

    base_prompt = "Extract customer name, pepper variety, Scoville SHU, and experience level (1-10)."
    if state["hint"]:
        base_prompt += f"\n\nCRITICAL HINT: {state['hint']}"

    msg = HumanMessage(content=[
        {"type": "text", "text": base_prompt},
        {"type": "media", "mime_type": "application/pdf", "data": state["pdf_base64"]}
    ])

    result = structured_llm.invoke([msg])
    return {"extraction": result, "retry_count": state["retry_count"] + 1}


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
    print(f"\n[DEBUG] Signature Found: {result.is_signed}")
    print(f"[DEBUG] Signature Confidence: {result.confidence}")

    return {"signature": result}


def manual_review_node(state: OrderState):
    sig_info = "Signature not yet analyzed"
    if state["signature"] is not None:
        sig_info = f"Signature confidence: {state['signature'].confidence}"

    print(f"\n[!] MANUAL REVIEW REQUIRED for {state['extraction'].customer_name}")
    print(f"Status: {sig_info}")

    choice = input("Approve this order anyway? (y/n): ")

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


def routing_logic(state: OrderState):
    if 0.1 < state["signature"].confidence < 0.7:
        return "manual_review"
    return "validate_safety"


def check_for_retry(state: OrderState):
    if state["extraction"].pepper_variety and state["extraction"].scoville_rating:
        return "verify_signature"

    if state["retry_count"] < 3:
        return "retry_extraction"

    return "fail_incomplete"


def extraction_router(state: OrderState):
    is_missing_data = not state["extraction"].pepper_variety or state["extraction"].scoville_rating is None

    if is_missing_data:
        if state["retry_count"] < 3:
            return "retry"
        else:
            print("\n[!] MAX RETRIES REACHED: Still missing data. Escalating to Manual Review.")
            return "manual_review"

    return "verify_signature"

workflow = StateGraph(OrderState)

workflow.add_node("extract_data", extraction_node)
workflow.add_node("verify_signature", signature_node)
workflow.add_node("validate_safety", safety_validation_node)
workflow.add_node("manual_review", manual_review_node)

workflow.set_entry_point("extract_data")

workflow.add_conditional_edges(
    "extract_data",
    extraction_router,
    {
        "retry": "extract_data",
        "verify_signature": "verify_signature",
        "manual_review": "manual_review"
    }
)

workflow.add_conditional_edges(
    "verify_signature",
    routing_logic,
    {
        "manual_review": "manual_review",
        "validate_safety": "validate_safety"
    }
)

workflow.add_edge("manual_review", END)
workflow.add_edge("validate_safety", END)

app = workflow.compile()

if __name__ == "__main__":
    with open("spicy_order.pdf", "rb") as f:
        pdf_data = base64.b64encode(f.read()).decode("utf-8")

    initial_state = {
        "pdf_base64": pdf_data,
        "extraction": None,
        "signature": None,
        "decision": "",
        "retry_count": 0,
        "hint": ""
    }

    print("--- Nate's Spicy Pepper One-Order Audit ---")
    final_state = app.invoke(initial_state)
    print(f"\nResult: {final_state['decision']}")


# todo Human-in-the-Loop with Persistent State
# todo Fact-Checking - google search to double check data