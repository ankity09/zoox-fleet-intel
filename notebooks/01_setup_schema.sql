-- Databricks notebook source
-- Zoox Fleet Intelligence — Schema Setup
-- Run this first to create the catalog schema.
--
-- ═══════════════════════════════════════════════════════════════════════════════
-- IMPORTANT: Multi-Statement Execution
-- ═══════════════════════════════════════════════════════════════════════════════
--
-- This file contains multiple SQL statements separated by "-- COMMAND ----------".
--
--   * NOTEBOOK UI:  Works fine — the notebook UI splits on "-- COMMAND ----------"
--     and sends each statement individually. Just click "Run All".
--
--   * API / CLI (Statement Execution API):  The Databricks Statement Execution API
--     (POST /api/2.0/sql/statements) only supports a SINGLE statement per request.
--     Sending multiple statements separated by ";" will fail with a parse error.
--     You must execute each statement below as a separate API call.
--
-- ═══════════════════════════════════════════════════════════════════════════════

-- COMMAND ----------

-- IMPORTANT: Statement 1 of 4 — Set catalog context
USE CATALOG serverless_simplot_v1_catalog;

-- COMMAND ----------

-- IMPORTANT: Statement 2 of 4 — Create schema
-- Zoox Fleet Intelligence — autonomous ride-hail fleet operations
CREATE SCHEMA IF NOT EXISTS zoox_fleet_intel
COMMENT 'Zoox Fleet Intelligence — autonomous ride-hail fleet operations across Las Vegas and San Francisco';

-- COMMAND ----------

-- IMPORTANT: Statement 3 of 4 — Set schema context
USE SCHEMA zoox_fleet_intel;

-- COMMAND ----------

-- IMPORTANT: Statement 4 of 4 — Verify schema is ready
SELECT current_catalog(), current_schema();
