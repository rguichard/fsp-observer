FROM python:3.13

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install -r requirements.txt --src=/pip-repos

COPY . /app

CMD ["python", "main.py"]
