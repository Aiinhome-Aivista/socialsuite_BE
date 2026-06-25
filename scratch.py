import sys
import os
sys.path.append('.')
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models import Post, PostTarget
import urllib.parse

try:
    pwd = urllib.parse.quote_plus('Dutta@2002')
    engine = create_engine(f'mysql+pymysql://root:{pwd}@localhost:3306/socialsuite')
    Session = sessionmaker(bind=engine)
    session = Session()

    with open("debug_output.txt", "w") as f:
        posts = session.query(Post).order_by(Post.id.desc()).limit(5).all()
        f.write('POSTS:\n')
        for p in posts:
            f.write(f'Post {p.id}: scheduled_at={p.scheduled_at}, status={p.status}\n')

        f.write('\nTARGETS:\n')
        for t in session.query(PostTarget).order_by(PostTarget.id.desc()).limit(5).all():
            f.write(f'Target {t.id}: post_id={t.post_id}, status={t.status}, error={t.error}\n')

except Exception as e:
    with open("debug_output.txt", "w") as f:
        f.write(f"EXCEPTION: {str(e)}\n")
