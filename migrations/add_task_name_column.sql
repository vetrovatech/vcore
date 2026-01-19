-- Migration script to add task_name column to promotor_tasks table
-- Run this SQL script on your MySQL database

-- Add task_name column after template_id
ALTER TABLE promotor_tasks 
ADD COLUMN task_name VARCHAR(200) NULL 
AFTER template_id;

-- Verify the column was added
DESCRIBE promotor_tasks;
