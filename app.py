from fastapi import FastAPI, Body, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from bson import ObjectId
from typing import Optional, List
import motor.motor_asyncio
from datetime import datetime

# Подключение к БД
app = FastAPI()
client = motor.motor_asyncio.AsyncIOMotorClient("mongodb://db:27017")
db = client.notes


# ObjectId из BSON не может быть декодирован в JSON, с которым работает FastApi
# Поэтому нужно преобразовать ObjectId элементы в строки, чтобы хранить их как _id
class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid objectid")
        return ObjectId(v)

    @classmethod
    def __modify_schema__(cls, field_schema):
        field_schema.update(type="string")


# Модель заметки
class NoteModel(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    created: Optional[datetime] = datetime.utcnow()
    updated: Optional[datetime] = None
    text: str = Field(...)
    author: str = Field(...)
    in_trash: bool = Field(...)

    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
        schema_extra = {
            "example": {
                "text": "Note's text",
                "created": "2021-09-20T00:02:03+00:00",
                "updated": "2021-09-20T00:02:03+00:00",
                "author": "Note's author",
                "in_trash": "False",
            }
        }


# Модель для изменения заметки
class UpdateNoteModel(BaseModel):
    created: Optional[datetime]
    updated: Optional[datetime]
    text: Optional[str]
    author: Optional[str]
    in_trash: Optional[bool]

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
        schema_extra = {
            "example": {
                "text": "Note's text",
                "created": "2021-09-20T00:02:03+00:00",
                "updated": "2021-09-20T00:02:03+00:00",
                "author": "Note's author",
                "in_trash": "False",
            }
        }


# Создание новой заметки
@app.post("/", response_description="Добавить новую заметку", response_model=NoteModel)
async def create_note(note: NoteModel = Body(...)):
    note = jsonable_encoder(note)
    new_note = await db["notes"].insert_one(note)
    created_note = await db["notes"].find_one({"_id": new_note.inserted_id})
    return JSONResponse(status_code=status.HTTP_201_CREATED, content=created_note)


# Список всех заметок
@app.get(
    "/", response_description="Список всех заметок", response_model=List[NoteModel]
)
async def list_all_notes():
    notes = await db["notes"].find({"in_trash": False}).to_list(1000)
    return JSONResponse(status_code=status.HTTP_200_OK, content=notes)


# Список заметок в корзине
@app.get(
    "/in_trash", response_description="Заметки из корзины", response_model=List[NoteModel]
)
async def list_deleted_notes():
    notes = await db["notes"].find({"in_trash": True}).to_list(1000)
    return JSONResponse(status_code=status.HTTP_200_OK, content=notes)


# Конкретная заметка по id
@app.get(
    "/{id}", response_description="Одна заметка", response_model=NoteModel
)
async def show_note(id: str):
    if (note := await db["notes"].find_one({"_id": id})) is not None:
        return JSONResponse(status_code=status.HTTP_200_OK, content=note)
    raise HTTPException(status_code=404, detail=f"Note {id} not found")


# Редактирование заметки
@app.put("/{id}", response_description="Редактирование заметки", response_model=NoteModel)
async def update_note(id: str, note: UpdateNoteModel = Body(...)):
    note = jsonable_encoder({k: v for k, v in note.dict().items() if v is not None})
    if len(note) >= 1:
        update_result = await db["notes"].update_one({"_id": id}, {"$set": note})
        if update_result.modified_count == 1:
            if (
                updated_note := await db["notes"].find_one({"_id": id})
            ) is not None:
                return JSONResponse(status_code=status.HTTP_200_OK, content=updated_note)
    if (existing_note := await db["notes"].find_one({"_id": id})) is not None:
        return JSONResponse(status_code=status.HTTP_200_OK, content=existing_note)
    raise HTTPException(status_code=404, detail=f"Note {id} not found")


# Перенести заметку в корзину
@app.put("/to_trash/{id}", response_description="Перенести заметку в корзину", response_model=NoteModel)
async def remove_note(id: str, note: UpdateNoteModel = Body(...)):
    note = {k: v for k, v in note.dict().items()}
    if not note["in_trash"]:
        await db["notes"].update_one({"_id": id}, {"$set": {"in_trash": True}})
        if (
            updated_note := await db["notes"].find_one({"_id": id})
        ) is not None:
            return JSONResponse(status_code=status.HTTP_200_OK, content=updated_note)
    raise HTTPException(status_code=404, detail=f"Note {id} not found")


# Перенести заметку из корзины
@app.put("/from_trash/{id}", response_description="Перенести заметку из корзины", response_model=NoteModel)
async def move_note(id: str, note: UpdateNoteModel = Body(...)):
    note = {k: v for k, v in note.dict().items()}
    if not note["in_trash"]:
        await db["notes"].update_one({"_id": id}, {"$set": {"in_trash": False}})
        if (
            updated_note := await db["notes"].find_one({"_id": id})
        ) is not None:
            return JSONResponse(status_code=status.HTTP_200_OK, content=updated_note)
    raise HTTPException(status_code=404, detail=f"Note {id} not found")


# Удалить заметку
@app.delete("/{id}", response_description="Удалить заметку")
async def delete_note(id: str):
    delete_result = await db["notes"].delete_one({"_id": id})
    if delete_result.deleted_count == 1:
        return JSONResponse(status_code=status.HTTP_204_NO_CONTENT)
    raise HTTPException(status_code=404, detail=f"Note {id} not found")
