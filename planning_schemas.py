from pydantic import BaseModel, Field
from typing import Literal

class Recommendation(BaseModel):
    id: str
    title: str = Field(min_length=1,max_length=90)
    slide_summary: str = Field(min_length=1,max_length=170)
    problem: str = Field(min_length=1,max_length=350)
    proposal: str = Field(min_length=1,max_length=500)
    benefit: str = Field(min_length=1,max_length=160)
    priority: Literal['P1','P2','P3']
    rationale: str = Field(min_length=1,max_length=350)
    tradeoff: str = Field(min_length=1,max_length=300)
    fact_ids: list[str] = Field(min_length=1,max_length=8)

class PlanTask(BaseModel):
    id: str
    recommendation_id: str
    phase: str = Field(min_length=1,max_length=70)
    priority: Literal['P1','P2','P3']
    task: str = Field(min_length=1,max_length=350)
    slide_summary: str = Field(min_length=1,max_length=150)
    deliverable: str = Field(min_length=1,max_length=300)
    acceptance: str = Field(min_length=1,max_length=300)
    owner_role: str = Field(min_length=1,max_length=130)
    start_week: int = Field(ge=1,le=52)
    duration_weeks: int = Field(ge=1,le=26)
    effort_person_days: float | None = Field(ge=0.25,le=520)
    depends_on: list[str] = Field(max_length=6)
    resources: str = Field(min_length=1,max_length=250)
    risk: str = Field(min_length=1,max_length=250)
    mitigation: str = Field(min_length=1,max_length=250)
    kpi: str = Field(min_length=1,max_length=250)
    assumptions: str = Field(min_length=1,max_length=350)
    fact_ids: list[str] = Field(min_length=1,max_length=8)

class ActionPlan(BaseModel):
    title: str = Field(min_length=1,max_length=180)
    assumptions: list[str] = Field(min_length=1,max_length=12)
    capacity_assumption: str = Field(min_length=1,max_length=450)
    approvals_required: list[str] = Field(min_length=1,max_length=8)
    recommendations: list[Recommendation] = Field(min_length=1,max_length=8)
    tasks: list[PlanTask] = Field(min_length=1,max_length=24)
