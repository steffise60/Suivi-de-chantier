from typing import Optional, List
from datetime import datetime, date
from fastapi import FastAPI, HTTPException, Header, Depends, Query, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from sqlmodel import SQLModel, Field, create_engine, Session, select
from pydantic import BaseModel
from sqlalchemy import func
import os
import shutil

- API_KEY = "changeme-dev-key"
+ API_KEY = os.getenv("API_KEY", "changeme-dev-key")


engine = create_engine(DB_URL, echo=False)

def require_key(x_api_key: Optional[str] = Header(default=None)):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")
    return True

# ------------------------------- Models -------------------------------
class ProjectBase(SQLModel):
    name: str
    client: Optional[str] = None
    start_date: date
    end_date: Optional[date] = None
    budget_hours: float = 0.0
    budget_cost: float = 0.0
    description: Optional[str] = None

class Project(ProjectBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

class ProjectCreate(ProjectBase): pass
class ProjectRead(ProjectBase): id: int

class TaskBase(SQLModel):
    project_id: int = Field(index=True, foreign_key="project.id")
    name: str
    planned_hours: float = 0.0
    planned_cost: float = 0.0
    start_date: Optional[date] = None
    end_date: Optional[date] = None

class Task(TaskBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

class TaskCreate(TaskBase): pass
class TaskRead(TaskBase): id: int

class TimeLogBase(SQLModel):
    project_id: int = Field(index=True, foreign_key="project.id")
    task_id: int = Field(foreign_key="task.id")
    work_date: date
    hours: float
    worker: Optional[str] = None
    note: Optional[str] = None

class TimeLog(TimeLogBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)

class TimeLogCreate(TimeLogBase): pass
class TimeLogRead(TimeLogBase):
    id: int
    created_at: datetime

class CostBase(SQLModel):
    project_id: int = Field(index=True, foreign_key="project.id")
    task_id: int = Field(foreign_key="task.id")
    cost_date: date
    amount: float
    category: str
    vendor: Optional[str] = None
    note: Optional[str] = None
    attachment_filename: Optional[str] = None  # <--- nouveau

class Cost(CostBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)

class CostCreate(CostBase): pass
class CostRead(CostBase):
    id: int
    created_at: datetime

# ------------------------------- App -------------------------------
app = FastAPI(title="API Suivi de Chantier", version="1.3.0")
app.mount("/attachments", StaticFiles(directory=ATT_DIR), name="attachments")

@app.on_event("startup")
def on_startup():
    SQLModel.metadata.create_all(engine)

def get_session():
    with Session(engine) as session:
        yield session

# ------------------------------- Projects -------------------------------
@app.post("/projects", response_model=ProjectRead, dependencies=[Depends(require_key)])
def create_project(payload: ProjectCreate, session: Session = Depends(get_session)):
    project = Project(**payload.dict())
    session.add(project)
    session.commit()
    session.refresh(project)
    return project

@app.get("/projects", response_model=List[ProjectRead], dependencies=[Depends(require_key)])
def list_projects(session: Session = Depends(get_session)):
    return session.exec(select(Project)).all()

@app.delete("/projects/{project_id}", status_code=204, dependencies=[Depends(require_key)])
def delete_project(project_id: int, session: Session = Depends(get_session)):
    obj = session.get(Project, project_id)
    if not obj:
        raise HTTPException(404, "Project not found")
    for tl in session.exec(select(TimeLog).where(TimeLog.project_id == project_id)).all():
        session.delete(tl)
    for c in session.exec(select(Cost).where(Cost.project_id == project_id)).all():
        # on peut supprimer le fichier joint si présent
        if c.attachment_filename:
            try:
                os.remove(os.path.join(ATT_DIR, c.attachment_filename))
            except FileNotFoundError:
                pass
        session.delete(c)
    for t in session.exec(select(Task).where(Task.project_id == project_id)).all():
        session.delete(t)
    session.delete(obj)
    session.commit()

# ------------------------------- Tasks -------------------------------
@app.post("/tasks", response_model=TaskRead, dependencies=[Depends(require_key)])
def create_task(payload: TaskCreate, session: Session = Depends(get_session)):
    if not session.get(Project, payload.project_id):
        raise HTTPException(404, "Related project not found")
    task = Task(**payload.dict())
    session.add(task)
    session.commit()
    session.refresh(task)
    return task

@app.get("/projects/{project_id}/tasks", response_model=List[TaskRead], dependencies=[Depends(require_key)])
def list_tasks(project_id: int, session: Session = Depends(get_session)):
    return session.exec(select(Task).where(Task.project_id == project_id)).all()

# ------------------------------- Time Logs -------------------------------
@app.post("/timelogs", response_model=TimeLogRead, dependencies=[Depends(require_key)])
def create_time_log(payload: TimeLogCreate, session: Session = Depends(get_session)):
    if not session.get(Project, payload.project_id):
        raise HTTPException(404, "Related project not found")
    if not session.get(Task, payload.task_id):
        raise HTTPException(404, "Related task not found")
    tl = TimeLog(**payload.dict())
    session.add(tl)
    session.commit()
    session.refresh(tl)
    return tl

@app.get("/projects/{project_id}/timelogs", response_model=List[TimeLogRead], dependencies=[Depends(require_key)])
def list_time_logs(project_id: int, session: Session = Depends(get_session)):
    return session.exec(select(TimeLog).where(TimeLog.project_id == project_id)).all()

# ------------------------------- Costs (JSON) -------------------------------
@app.post("/costs", response_model=CostRead, dependencies=[Depends(require_key)])
def create_cost(payload: CostCreate, session: Session = Depends(get_session)):
    if not session.get(Project, payload.project_id):
        raise HTTPException(404, "Related project not found")
    if not session.get(Task, payload.task_id):
        raise HTTPException(404, "Related task not found")
    c = Cost(**payload.dict())
    session.add(c)
    session.commit()
    session.refresh(c)
    return c

@app.get("/projects/{project_id}/costs", response_model=List[CostRead], dependencies=[Depends(require_key)])
def list_costs(project_id: int, session: Session = Depends(get_session)):
    return session.exec(select(Cost).where(Cost.project_id == project_id)).all()

# ------------------------------- Costs with file (multipart) -------------------------------
@app.post("/costs-with-file", response_model=CostRead, dependencies=[Depends(require_key)])
def create_cost_with_file(
    project_id: int = Form(...),
    task_id: int = Form(...),
    cost_date: date = Form(...),
    amount: float = Form(...),
    category: str = Form(...),
    vendor: Optional[str] = Form(None),
    note: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    session: Session = Depends(get_session)
):
    # validations
    if not session.get(Project, project_id):
        raise HTTPException(404, "Related project not found")
    task = session.get(Task, task_id)
    if not task:
        raise HTTPException(404, "Related task not found")
    if file:
        if file.content_type not in ("application/pdf",):
            raise HTTPException(415, "Only PDF files are allowed")
        # nom de fichier: cost_<proj>_<task>_<timestamp>.pdf
        base = f"cost_{project_id}_{task_id}_{int(datetime.utcnow().timestamp())}.pdf"
        dest = os.path.join(ATT_DIR, base)
        with open(dest, "wb") as out:
            shutil.copyfileobj(file.file, out)
        attachment_filename = base
    else:
        attachment_filename = None

    c = Cost(
        project_id=project_id,
        task_id=task_id,
        cost_date=cost_date,
        amount=amount,
        category=category,
        vendor=vendor,
        note=note,
        attachment_filename=attachment_filename,
    )
    session.add(c)
    session.commit()
    session.refresh(c)
    return c

# ------------------------------- KPI -------------------------------
class KPIResponse(BaseModel):
    project_id: int
    total_hours: float
    total_cost: float
    budget_hours: float
    budget_cost: float
    hours_variance: float
    cost_variance: float

@app.get("/projects/{project_id}/kpi", response_model=KPIResponse, dependencies=[Depends(require_key)])
def project_kpi(project_id: int, session: Session = Depends(get_session)):
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    total_hours = session.exec(select(func.coalesce(func.sum(TimeLog.hours), 0.0)).where(TimeLog.project_id == project_id)).one()
    total_cost = session.exec(select(func.coalesce(func.sum(Cost.amount), 0.0)).where(Cost.project_id == project_id)).one()
    return KPIResponse(
        project_id=project_id,
        total_hours=total_hours,
        total_cost=total_cost,
        budget_hours=project.budget_hours,
        budget_cost=project.budget_cost,
        hours_variance=total_hours - project.budget_hours,
        cost_variance=total_cost - project.budget_cost,
    )
from random import randint

@app.post("/seed", dependencies=[Depends(require_key)])
def seed(session: Session = Depends(get_session)):
    # 1) Crée un projet démo
    prj = Project(
        name="Projet Démo",
        client="Client Démo",
        start_date=date.today().replace(day=1),
        end_date=date.today(),
        budget_hours=120.0,
        budget_cost=15000.0,
        description="Projet injecté par /seed"
    )
    session.add(prj); session.commit(); session.refresh(prj)

    # 2) Deux tâches
    t1 = Task(project_id=prj.id, name="Gros œuvre", planned_hours=60, planned_cost=8000)
    t2 = Task(project_id=prj.id, name="Second œuvre", planned_hours=60, planned_cost=7000)
    session.add(t1); session.add(t2); session.commit(); session.refresh(t1); session.refresh(t2)

    # 3) Temps (quelques logs)
    for _ in range(3):
        tl = TimeLog(project_id=prj.id, task_id=t1.id, work_date=date.today(), hours=randint(2, 6), worker="Équipe A")
        session.add(tl)
    for _ in range(2):
        tl = TimeLog(project_id=prj.id, task_id=t2.id, work_date=date.today(), hours=randint(3, 5), worker="Équipe B")
        session.add(tl)

    # 4) Coûts (sans fichier pour l’exemple)
    c1 = Cost(project_id=prj.id, task_id=t1.id, cost_date=date.today(), amount=2500, category="materiel", vendor="Brico", note="Matériaux")
    c2 = Cost(project_id=prj.id, task_id=t2.id, cost_date=date.today(), amount=1800, category="sous-traitance", vendor="Sous-Traitant X")
    session.add(c1); session.add(c2)

    session.commit()
    return {"project_id": prj.id}
