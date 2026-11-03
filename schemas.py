from pydantic import BaseModel, Field
from typing import Literal

class Fact(BaseModel):
    text: str = Field(min_length=1)
    quote: str = Field(min_length=1)
    source_ids: list[str] = Field(min_length=1)

class TranscriptSection(BaseModel):
    title: str = Field(min_length=1,max_length=110)
    start_source_id: str = Field(min_length=1,max_length=40)

class Extraction(BaseModel):
    facts: list[Fact]
    transcript_sections: list[TranscriptSection] = Field(default_factory=list,max_length=30)

class Claim(BaseModel):
    text: str = Field(min_length=1, max_length=1200)
    fact_ids: list[str] = Field(min_length=1)

class Action(BaseModel):
    task: str
    owner: str
    due: str
    fact_ids: list[str] = Field(min_length=1)

class Slide(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    bullets: list[Claim] = Field(min_length=1, max_length=6)
    notes: str
    layout: Literal['auto','cover','overview','findings','comparison','process','risk','decisions','actions'] = 'auto'


class Topic(BaseModel):
    title: str = Field(min_length=1,max_length=90)
    points: list[Claim] = Field(min_length=1,max_length=6)
    status: Claim | None = None
    slide_summary: str = Field(default='',max_length=220)


class Highlight(BaseModel):
    value: str = Field(min_length=1,max_length=40)
    label: str = Field(min_length=1,max_length=150)
    fact_ids: list[str] = Field(min_length=1)


class RiskFinding(BaseModel):
    title: str = Field(min_length=1,max_length=90)
    description: str = Field(min_length=1,max_length=500)
    impact: str = Field(min_length=1,max_length=300)
    mitigation: str = Field(min_length=1,max_length=350)
    level: Literal['Tinggi','Sedang','Rendah','Belum dinilai']
    assessment_basis: Literal['Dinyatakan dalam sumber','Analisis usulan']
    fact_ids: list[str] = Field(min_length=1)
    slide_impact: str = Field(default='',max_length=150)
    slide_mitigation: str = Field(default='',max_length=180)

class Report(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    summary: list[Claim] = Field(min_length=1)
    decisions: list[Claim]
    actions: list[Action]
    uncertainties: list[str]
    slides: list[Slide] = Field(min_length=0, max_length=16)
    context: list[Claim] = Field(default_factory=list,max_length=5)
    executive_slide_summary: list[Claim] = Field(default_factory=list,max_length=3)
    topics: list[Topic] = Field(default_factory=list,max_length=12)
    outcomes: list[Claim] = Field(default_factory=list,max_length=12)
    conclusions: list[Claim] = Field(default_factory=list,max_length=8)
    open_decisions: list[Claim] = Field(default_factory=list,max_length=10)
    risk_items: list[RiskFinding] = Field(default_factory=list,max_length=12)
    highlights: list[Highlight] = Field(default_factory=list,max_length=4)
    meeting_date: Claim | None = None
    participants: list[Claim] = Field(default_factory=list,max_length=16)

class Review(BaseModel):
    passed: bool
    issues: list[str]
class SummaryReport(Report):
    slides: list[Slide] = Field(max_length=0)


class FactCorrection(Fact):
    id: str = Field(pattern=r'^F\d{4,}$')


class QualityRepair(BaseModel):
    report: Report
    fact_updates: list[FactCorrection]
    additional_facts: list[FactCorrection]
