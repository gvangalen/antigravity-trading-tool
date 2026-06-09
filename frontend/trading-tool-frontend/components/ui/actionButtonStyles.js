import clsx from "clsx";

const baseStyles =
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-xl border text-sm font-semibold transition-colors active:scale-[0.99] disabled:cursor-not-allowed disabled:opacity-50";

const sizeStyles = {
  md: "min-h-11 px-4 py-2.5",
  sm: "min-h-9 px-3 py-2 text-sm",
  icon: "h-10 w-10 p-0",
  chip: "min-h-8 px-3 py-1.5 text-xs",
};

const variantStyles = {
  primary:
    "border-blue-600 bg-blue-600 text-white shadow-sm shadow-blue-600/15 hover:bg-blue-700 hover:border-blue-700",
  secondary:
    "border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-950 text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-900",
  danger:
    "border-rose-600 bg-rose-600 text-white shadow-sm shadow-rose-600/15 hover:bg-rose-700 hover:border-rose-700",
  ghost:
    "border-transparent bg-transparent text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-900",
  chip:
    "border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-600 dark:text-slate-300 hover:border-blue-200 hover:text-blue-700 dark:hover:text-blue-300",
  icon:
    "border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-950 text-slate-500 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-900",
};

/**
 * @param {{variant?: keyof typeof variantStyles, size?: keyof typeof sizeStyles, className?: string}} options
 */
export function actionButtonStyles({
  variant = "primary",
  size = "md",
  className,
} = {}) {
  return clsx(baseStyles, sizeStyles[size], variantStyles[variant], className);
}
