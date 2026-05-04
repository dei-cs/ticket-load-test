from peewee import *
import os

DATABASE_URL = os.getenv("DATABASE_URL")

db = PostgresqlDatabase(DATABASE_URL)

class BaseModel(Model):
    class Meta:
        database = db


class Ticket(BaseModel):
    class Meta:
        table_name = 'tickets'

    id = AutoField()
    event_type = TextField()
    owner = TextField(null=True)
    state = TextField() # available // reserved // sold
    reserved_at = DateTimeField(null=True)