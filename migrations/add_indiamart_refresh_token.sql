-- Migration: add refresh_token column to indiamart_tokens
-- Run once against your MySQL database

ALTER TABLE indiamart_tokens
    ADD COLUMN refresh_token TEXT NULL AFTER ak_token;
