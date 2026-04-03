from peewee import chunked
from data.db import User, db
from utils.user_gen import generate_user

def populate_user_table(count: int):
    db.connect(reuse_if_open=True)
    db.create_tables([User], safe=True)
    add_users = [generate_user() for _ in range(count)]
    with db.atomic():
        for batch in chunked(add_users, 100):
            User.insert_many(batch).execute()

    db.close()
    
def get_users(count: int, starting_index: int = 0):
    db.connect(reuse_if_open=True)
    users = list(
        User.select()
            .where(User.id > starting_index)
            .order_by(User.id)
            .limit(count)
            .dicts()
    )
    db.close
    return users

def delete_all_users_query():
    db.connect(reuse_if_open=True)
    delete_count = User.delete().execute()
    db.close()
    return delete_count