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
