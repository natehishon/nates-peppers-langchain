from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime
import uuid

class OrderMetadata(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    customer_name: str
    pdf_url: str
    decision: str = "Pending"
    pepper_variety: Optional[str] = None
    scoville_rating: Optional[int] = None
    status: str = "PROCESSING"
    created_at: datetime = Field(default_factory=datetime.utcnow)

