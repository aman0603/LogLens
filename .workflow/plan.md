# Phase Plan

## Goal
Transform LogLens from a log storage platform into an intelligent search platform by implementing an embedding pipeline that converts log messages into vectors, stores them in Qdrant, and exposes semantic retrieval APIs alongside existing keyword search.

## Scope
- Implement embedding generation service (uses sentence-transformers or similar)
- Integrate with Qdrant vector database for storage
- Create asynchronous pipeline to process logs from Kafka and generate embeddings
- Build semantic search API endpoints
- Ensure keyword search continues to work independently
- Design reusable retrieval pipeline for future AI features
- Update Docker Compose to include Qdrant service
- Maintain structured logging throughout

## Out of scope
- Incident clustering
- AI summaries
- Root cause analysis
- Timelines
- Conversational investigation

## Tasks
1. Add Qdrant service to docker-compose.yml
2. Create embedding service that consumes logs from Kafka and generates vector embeddings
3. Modify storage consumer to also publish embeddings to a separate Kafka topic (or use same with different topic)
4. Create Qdrant storage service that consumes embeddings and stores them with payload
5. Implement semantic search API endpoint in API service
6. Ensure keyword search endpoint remains unchanged and functional
7. Add comprehensive structured logging to all new components
8. Write integration tests to verify both search types work
9. Update documentation with new architecture decisions

## Acceptance criteria
- [ ] Every stored log entry has a corresponding vector embedding in Qdrant
- [ ] Embedding generation happens asynchronously without blocking ingestion pipeline
- [ ] Semantic search returns logs ranked by similarity score to query
- [ ] Keyword search continues to return exact matches as before
- [ ] Search APIs return structured results with metadata
- [ ] Retrieval pipeline components can be reused by future AI features (embedding service, Qdrant client)
- [ ] Docker Compose starts all services including Qdrant
- [ ] System maintains idempotency and handles duplicate messages gracefully

## Approval
- State: pending
- Approved by: —
- Approved at: —
