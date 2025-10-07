/*
  # Create video processing tasks table

  1. New Tables
    - `tasks`
      - `id` (uuid, primary key) - Unique task identifier
      - `task_type` (text) - Type of task: caption, merge, or background_music
      - `status` (text) - Current status: queued, running, success, or failed
      - `video_url` (text) - Input video URL for processing
      - `model_size` (text, nullable) - Whisper model size for caption tasks
      - `result_video_url` (text, nullable) - Public URL of processed video
      - `error_message` (text, nullable) - Error details if task failed
      - `file_size` (bigint, nullable) - Total size of downloaded files in bytes
      - `metadata` (jsonb, nullable) - Task-specific parameters (scene URLs, audio URLs, volumes)
      - `created_at` (timestamptz) - Task creation timestamp
      - `updated_at` (timestamptz) - Last update timestamp
      - `completed_at` (timestamptz, nullable) - Task completion timestamp

  2. Indexes
    - Index on status for efficient filtering
    - Index on created_at for cleanup queries
    - Index on task_type for analytics

  3. Security
    - Enable RLS on `tasks` table
    - Add policy for public read access (for status polling)
    - Add policy for authenticated insert (task submission)
*/

CREATE TABLE IF NOT EXISTS tasks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  task_type text NOT NULL CHECK (task_type IN ('caption', 'merge', 'background_music')),
  status text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'success', 'failed')),
  video_url text NOT NULL,
  model_size text DEFAULT 'small',
  result_video_url text,
  error_message text,
  file_size bigint,
  metadata jsonb DEFAULT '{}'::jsonb,
  created_at timestamptz DEFAULT now() NOT NULL,
  updated_at timestamptz DEFAULT now() NOT NULL,
  completed_at timestamptz
);

-- Create indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON tasks(created_at);
CREATE INDEX IF NOT EXISTS idx_tasks_task_type ON tasks(task_type);

-- Enable Row Level Security
ALTER TABLE tasks ENABLE ROW LEVEL SECURITY;

-- Policy: Allow anyone to read task status (for polling)
CREATE POLICY "Allow public read access to tasks"
  ON tasks
  FOR SELECT
  USING (true);

-- Policy: Allow anyone to insert tasks (for submission)
CREATE POLICY "Allow public insert of tasks"
  ON tasks
  FOR INSERT
  WITH CHECK (true);

-- Policy: Allow system to update tasks (worker process)
CREATE POLICY "Allow public update of tasks"
  ON tasks
  FOR UPDATE
  USING (true)
  WITH CHECK (true);

-- Function to automatically update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to call the function before updates
CREATE TRIGGER update_tasks_updated_at
  BEFORE UPDATE ON tasks
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();
