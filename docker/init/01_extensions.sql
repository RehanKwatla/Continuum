-- Extensions required by Continuum.
-- pgvector: reserved for Phase 3 embeddings (no vectors are stored yet).
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Dedicated database used by the automated test-suite.
SELECT 'CREATE DATABASE continuum_test OWNER continuum'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'continuum_test')\gexec
