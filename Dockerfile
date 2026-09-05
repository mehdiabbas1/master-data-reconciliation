FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY pyproject.toml .
COPY src/ src/
COPY data/generate.py data/generate.py

ENV PYTHONPATH=/app/src

# Generate a dataset and reconcile it. Mount your own CSVs over /app/data
# and override the command to run against real files.
CMD ["sh", "-c", "python data/generate.py -n 4000 -o data && python -m mdr.cli --legacy data/legacy_master.csv --erp data/erp_master.csv --truth data/ground_truth.csv --out out"]
