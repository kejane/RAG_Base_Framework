import requests

ES_HOST = "http://localhost:9200"
INDICES = "wp_event,gpu,llm,paper,sota,topic,wp_dataset,wp_notebook,wp_post,wp_wiki"

def search_es(query: str, topk: int = 5):
    payload = {
        "size": topk,
        "query": {
            "multi_match": {
                "query": query,
                "fields": ["all_text"]
            }
        }
    }
    r = requests.get(f"{ES_HOST}/{INDICES}/_search", json=payload)
    r.raise_for_status()
    hits = r.json()["hits"]["hits"]
    return hits


if __name__ == "__main__":
    for hit in search_es("comfyui"):
        print(hit)
        print("\n")