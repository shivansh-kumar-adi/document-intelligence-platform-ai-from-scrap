# Evaluation

`POST /api/v1/evaluation` accepts real benchmark cases containing a question and expected document IDs. It executes retrieval and calculates Recall@K, Precision@K, Mean Reciprocal Rank and mean retrieval latency. Results are returned, not pre-populated or fabricated.

Example:

```json
{"top_k":5,"cases":[{"question":"What is the retention period?","expected_document_ids":["DOCUMENT_UUID"]}]}
```

Citation coverage can be derived from chat responses as the proportion of grounded answers containing at least one returned citation. A portfolio evaluation should preserve the dataset, machine details, model name, parameters and raw response JSON.

