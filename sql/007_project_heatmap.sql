-- 007_project_heatmap.sql
-- 项目热力矩阵聚合表：subject × date 粒度，含预计算的关联/竞品数据
-- 由 stages/aggregate_projects.py 在 pipeline archive 阶段之后写入

CREATE TABLE IF NOT EXISTS project_heatmap_data (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,

  -- subject 维度
  subject_id uuid REFERENCES subjects(id),
  subject_slug text NOT NULL,
  subject_name text NOT NULL,
  subject_type text NOT NULL,          -- project / product / org

  -- track 维度（通过 tag/keyword 匹配得出，可为空）
  track_id uuid,
  track_name text,
  track_group text,                    -- infrastructure / agent / devtools / application / industry

  -- 时间维度
  snapshot_date date NOT NULL,

  -- 分数
  score double precision,              -- 原始 aha_index (0-1)
  score_100 double precision,          -- score * 100，前端展示用

  -- 来源信息
  role text,                           -- primary / mentioned
  source_name text,

  -- 内容元数据（冗余存储，避免前端再 JOIN）
  tags text[],
  summary text,

  -- subject 聚合信息
  first_seen_at date,
  last_seen_at date,
  mention_count integer,

  -- 预计算的关联项目数据（一级关联 + timeline）
  -- 结构: { "related": [...], "competitors": [...] }
  related_data jsonb,

  created_at timestamptz DEFAULT now(),

  UNIQUE(subject_id, snapshot_date)
);

CREATE INDEX IF NOT EXISTS idx_phd_track_date ON project_heatmap_data(track_id, snapshot_date);
CREATE INDEX IF NOT EXISTS idx_phd_subject ON project_heatmap_data(subject_id);
CREATE INDEX IF NOT EXISTS idx_phd_date ON project_heatmap_data(snapshot_date);
