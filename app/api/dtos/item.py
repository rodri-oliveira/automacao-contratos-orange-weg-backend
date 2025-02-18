from pydantic import BaseModel

class Item(BaseModel): 
    id: int
    description: str

class ItemFormDto(BaseModel): 
    description: str
