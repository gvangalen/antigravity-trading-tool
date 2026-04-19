"use client";

import { useEffect, useState } from "react";
import { ChevronsUp } from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";

export default function ScrollToTop() {
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    const toggleVisibility = () => {
      if (window.scrollY > 400) {
        setIsVisible(true);
      } else {
        setIsVisible(false);
      }
    };

    window.addEventListener("scroll", toggleVisibility);
    return () => window.removeEventListener("scroll", toggleVisibility);
  }, []);

  const scrollToTop = () => {
    window.scrollTo({
      top: 0,
      behavior: "smooth",
    });
  };

  return (
    <AnimatePresence>
      {isVisible && (
        <motion.button
          initial={{ opacity: 0, y: 20, scale: 0.8 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 20, scale: 0.8 }}
          onClick={scrollToTop}
          className="fixed bottom-8 left-[calc(50%+128px)] -translate-x-1/2 z-50 p-3 rounded-full bg-slate-900/90 text-white shadow-2xl backdrop-blur-md border border-slate-700/50 hover:bg-blue-600 hover:-translate-y-1 transition-all duration-300 group"
          aria-label="Scroll to top"
        >
          <ChevronsUp 
            size={20} 
            className="transition-transform duration-300 group-hover:scale-110" 
          />
        </motion.button>
      )}
    </AnimatePresence>
  );
}
