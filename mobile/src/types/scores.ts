export type ScoreCategory = 'Macro' | 'Market' | 'Technical' | 'Setup';

export type Score = {
  label: ScoreCategory;
  value: number;
  status: string;
};

export type TodayScores = {
  scores: Score[];
  aiSummary: string;
};

export type DomainScore = {
  label: ScoreCategory;
  score: number;
  trend: string;
  summary: string;
  tone: 'success' | 'warning' | 'danger' | 'accent' | 'neutral';
};
