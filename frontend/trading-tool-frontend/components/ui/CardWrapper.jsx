"use client";

export default function CardWrapper({ title, children, icon, className = "" }) {
  return (
    <div className={`card ${className}`}>
      {/* 🟢 CARD HEADER */}
      {title && (
        <div className="card-header">
           <div className="card-title">
              {icon && <span className="text-blue-600">{icon}</span>}
              <span>{title}</span>
           </div>
        </div>
      )}

      {/* 📄 CARD CONTENT */}
      <div className="card-p">
        {children}
      </div>
    </div>
  );
}
