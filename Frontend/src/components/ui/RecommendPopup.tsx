import React, { useState } from "react";

interface RecommendPopupProps {
  isOpen: boolean;
  onClose: () => void;
  onSend: (type: "role" | "team", selection: string) => void;
}

export default function RecommendPopup({
  isOpen,
  onClose,
  onSend,
}: RecommendPopupProps) {
  const [activeTab, setActiveTab] = useState<"role" | "team">("role");
  const [selection, setSelection] = useState("");

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center px-4">
      {/* backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />

      <div
        className="relative z-10 w-full max-w-3xl rounded-2xl bg-white shadow-[0_30px_60px_rgba(0,0,0,0.45)]"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between p-6 border-b border-gray-100">
          <h3 className="text-xl font-semibold text-gray-800">
            Refer this Candidate
          </h3>
          <button
            onClick={onClose}
            aria-label="Close"
            className="ml-4 inline-flex h-9 w-9 items-center justify-center rounded-full hover:bg-gray-100"
          >
            <svg
              className="h-4 w-4 text-gray-600"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        {/* Body */}
        <div className="px-8 py-6">
          {/* Tab buttons */}
          <div className="mb-6 flex gap-4">
            <button
              onClick={() => setActiveTab("role")}
              className={`px-4 py-2 rounded-md text-sm font-medium border ${
                activeTab === "role"
                  ? "bg-[#F8FEFE] border-[#CCE7E8] text-[#0B7285]"
                  : "bg-white border-gray-200 text-gray-600"
              }`}
            >
              Recommend to Role
            </button>
            <button
              onClick={() => setActiveTab("team")}
              className={`px-4 py-2 rounded-md text-sm font-medium border ${
                activeTab === "team"
                  ? "bg-[#F8FEFE] border-[#CCE7E8] text-[#0B7285]"
                  : "bg-white border-gray-200 text-gray-600"
              }`}
            >
              Recommend to Team
            </button>
          </div>

          {/* Dropdown */}
          <div>
            <select
              value={selection}
              onChange={(e) => setSelection(e.target.value)}
              className="w-full rounded-md border border-[#E6F0F0] bg-white px-4 py-3 text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-[#D6EEF0]"
            >
              <option value="">Select a Role/ teammate</option>
              <option value="frontend">Frontend Developer</option>
              <option value="backend">Backend Developer</option>
              <option value="ml">ML Engineer</option>
              <option value="teammate1">Teammate 1</option>
              <option value="teammate2">Teammate 2</option>
            </select>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-4 px-8 py-5 border-t border-gray-100">
          <button
            onClick={() => {
              if (selection) {
                onSend(activeTab, selection);
                onClose();
              }
            }}
            className="inline-flex items-center justify-center rounded-md bg-[#007BFF] px-5 py-2 text-sm font-semibold text-white shadow-sm hover:brightness-95"
          >
            Send
          </button>
        </div>
      </div>
    </div>
  );
}
