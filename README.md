# AgriMarketEnv

Real-world OpenEnv environment simulating agricultural supply chain.

## Run
pip install -r requirements.txt
python inference.py

## Docker
docker build -t agrimarket .
docker run -p 7860:7860 agrimarket