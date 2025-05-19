from pathlib import Path
from typing import List, Dict, Any
from pydantic import BaseModel, ValidationError
import json

class Criterion(BaseModel):
    name: str
    type: str
    weight: float
    scale: list

class InputData(BaseModel):
    alternatives: List[str]
    criteria: List[Dict[str, Any]]
    experts: List[str]
    ratings: List[Dict[str, Any]]

def parse_input(json_path: Path) -> InputData:
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return InputData(**data)
    except ValidationError as e:
        print(f"Ошибка валидации: {e}")
        raise