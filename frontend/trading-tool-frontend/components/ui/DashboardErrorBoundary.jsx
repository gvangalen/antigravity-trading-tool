"use client";

import React, { Component } from 'react';
import { AlertTriangle, RefreshCcw } from 'lucide-react';
import { I18nContext } from "@/app/providers/I18nProvider";

/**
 * 🧱 DashboardErrorBoundary — localized safety for widgets
 * Catches rendering errors in children and shows a clean fallback.
 */
class DashboardErrorBoundary extends Component {
  static contextType = I18nContext;

  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error("❌ Widget Crash Detected:", error, errorInfo);
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null });
    if (this.props.onRetry) {
      this.props.onRetry();
    }
  };

  render() {
    const copy = this.context?.t?.ui?.errorBoundary || {};
    if (this.state.hasError) {
      return (
        <div className="card bg-white dark:bg-[#0f172a] border-2 border-rose-100 dark:border-rose-900/30 rounded-3xl p-8 flex flex-col items-center justify-center text-center min-h-[200px] transition-all duration-300">
          <div className="w-12 h-12 bg-rose-50 dark:bg-rose-950/30 rounded-full flex items-center justify-center mb-4">
            <AlertTriangle className="text-rose-500" size={24} />
          </div>
          <h3 className="text-sm font-black text-slate-900 dark:text-slate-100 uppercase tracking-widest mb-2">
            {copy.title}
          </h3>
          <p className="text-xs text-slate-500 dark:text-slate-400 max-w-[240px] mb-6 leading-relaxed">
            {copy.body}
          </p>
          <button
            onClick={this.handleRetry}
            className="flex items-center gap-2 px-4 py-2 bg-slate-900 dark:bg-slate-100 text-white dark:text-slate-900 rounded-xl text-[10px] font-black uppercase tracking-widest hover:opacity-80 transition-opacity"
          >
            <RefreshCcw size={12} />
            {copy.retry}
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}

export default DashboardErrorBoundary;
