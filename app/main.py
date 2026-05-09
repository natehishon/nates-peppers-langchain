from fastapi import FastAPI, HTTPException, Depends
from sqlmodel import Session, select
from langgraph.types import Command

from .database import engine, checkpointer, pool
from .models import OrderMetadata
from .graph import graph
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

from pydantic import BaseModel

app = FastAPI(title="Nate's Spicy Audit API")

# For dev only
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class AuditRequest(BaseModel):
    customer_name: str
    pdf_url: str


@app.on_event("startup")
def on_startup():
    from sqlmodel import SQLModel
    SQLModel.metadata.create_all(engine)
    checkpointer.setup()


@app.on_event("shutdown")
def on_shutdown():
    pool.close()


import uuid
import boto3
from fastapi import File, UploadFile, Form

s3_client = boto3.client('s3')
BUCKET_NAME = "nates-peppers"
REGION = "us-east-2"


@app.post("/audit/start")
async def start_audit(
        customer_name: str = Form(...),
        file: UploadFile = File(...)
):
    thread_id = str(uuid.uuid4())
    s3_key = f"audits/{thread_id}_{file.filename}"

    s3_client.upload_fileobj(
        file.file,
        BUCKET_NAME,
        s3_key,
        ExtraArgs={
            "ContentType": file.content_type
        }
    )

    pdf_url = f"https://{BUCKET_NAME}.s3.{REGION}.amazonaws.com/{s3_key}"

    with Session(engine) as session:
        new_order = OrderMetadata(id=thread_id, customer_name=customer_name, pdf_url=pdf_url)
        session.add(new_order)
        session.commit()

    try:
        config = {"configurable": {"thread_id": thread_id}}

        runnable = graph.with_config(config)
        initial_state = {
            "pdf_url": pdf_url,
            "extraction": None,
            "decision": "",
            "retry_count": 0
        }

        result = runnable.invoke(initial_state, checkpointer=checkpointer)
        current_state = graph.get_state(config)

        with Session(engine) as session:
            db_order = session.get(OrderMetadata, thread_id)
            if db_order:
                if "manual_review" in current_state.next:
                    db_order.status = "Awaiting Review"
                    if "extraction" in current_state.values:
                        ext = current_state.values["extraction"]
                        db_order.pepper_variety = ext.pepper_variety
                        db_order.scoville_rating = ext.scoville_rating
                else:
                    db_order.status = current_state.values.get("decision", "COMPLETED")

                session.add(db_order)
                session.commit()

        return {"thread_id": thread_id, "status": "Success", "decision": result.get("decision")}

    except Exception as e:
        with Session(engine) as session:
            db_order = session.get(OrderMetadata, thread_id)
            if db_order:
                db_order.status = "FAILED"
                session.add(db_order)
                session.commit()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/audit/{thread_id}/resume")
def resume_audit(thread_id: str, human_decision: str):
    config = {"configurable": {"thread_id": thread_id}}

    history = list(graph.get_state_history(config))

    for state in history:
        print(f"ID: {state.config['configurable']['checkpoint_id']}")
        print(f"Next Node: {state.next}")
        print(f"Values: {state.values}\n---")

    with Session(engine) as session:
        order = session.exec(select(OrderMetadata).where(OrderMetadata.id == thread_id)).first()
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

    try:
        graph.invoke(
            Command(resume=human_decision),
            config=config,
            checkpointer=checkpointer
        )

        with Session(engine) as session:
            order.status = "Completed"
            order.decision = human_decision
            session.add(order)
            session.commit()

        return {"status": "Resumed", "final_decision": human_decision}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/orders")
def get_orders():
    with Session(engine) as session:
        return session.exec(select(OrderMetadata)).all()
