from fastapi import APIRouter, HTTPException, Security
from starlette import status
from app.api.dtos.item import Item, ItemFormDto
from app.core.security import TokenData, auth

router = APIRouter()

items: dict[int, Item] = {}
index: int = 0

@router.get("/{id}", response_model=Item)
async def getItem(id: int):
    item = items.get(id)

    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    return item

@router.post("/", response_model=Item)
async def postItem(formDto: ItemFormDto, token: TokenData = Security(auth.verify)):
    global index
    current_index = index
    item = Item(description=formDto.description, id=current_index)
    items.update({ index: item} )

    index = current_index  + 1

    return item

@router.put("/{id}", response_model=Item)
async def putItem(id: int, formDto: ItemFormDto, token: TokenData = Security(auth.verify)):
    item = items.get(id)

    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    new_item = Item(description=formDto.description, id=id)
    items[id] = new_item

    return new_item

@router.delete("/{id}", response_model=Item)
async def deleteItem(id: int, token: TokenData = Security(auth.verify, scopes=["admin"])):
    item = items.get(id)

    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    del items[id];

    return item