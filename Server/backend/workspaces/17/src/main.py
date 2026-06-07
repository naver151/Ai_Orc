from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from typing import List

app = FastAPI()

# In-memory database to store calculation history
calculation_history = []

# Pydantic model for calculation records
class CalculationRecord(BaseModel):
    operation: str
    operands: List[float]
    result: float

@app.post('/calculate', response_model=CalculationRecord)
def calculate(record: CalculationRecord):
    """Perform a calculation and save the record."""
    # Here we assume the result has already been calculated and provided in the payload
    calculation_history.append(record)
    return record

@app.get('/history', response_model=List[CalculationRecord])
def get_history():
    """Fetch the calculation history."""
    return calculation_history

@app.get('/')
def root():
    return {"message": "Welcome to the calculator API!"}