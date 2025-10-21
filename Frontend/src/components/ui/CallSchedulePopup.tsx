// CallSchedulePopup.tsx
import React, { useEffect, useRef, useState } from "react";

type CallSchedulePopupProps = {
  isOpen: boolean;
  onClose: () => void;
  candidateName?: string;
  /**
   * onSend will be called with the message text and the active channel ("whatsapp" | "email")
   */
  onSend: (message: string, channel?: "whatsapp" | "email") => void;
  /**
   * optional initial message to prefill the textarea
   */
  initialMessage?: string;
};

export default function CallSchedulePopup({
  isOpen,
  onClose,
  candidateName = "Candidate",
  onSend,
  initialMessage = "",
}: CallSchedulePopupProps) {
  const [message, setMessage] = useState<string>(initialMessage);
  const [activeTab, setActiveTab] = useState<"whatsapp" | "email">("whatsapp");
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    setMessage(initialMessage);
  }, [initialMessage, isOpen]);

  useEffect(() => {
    if (isOpen) {
      // focus textarea when modal opens
      setTimeout(() => textareaRef.current?.focus(), 50);
      // lock scroll
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [isOpen]);

  // close on Escape
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape" && isOpen) onClose();
      // quick send: Ctrl/Cmd + Enter
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter" && isOpen) {
        e.preventDefault();
        handleSend();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, message, activeTab]);

  function handleSend() {
    const trimmed = message.trim();
    if (!trimmed) {
      // simple validation: don't send empty message
      // optional: show toast / inline error
      textareaRef.current?.focus();
      return;
    }
    onSend(trimmed, activeTab);
    // optionally clear message after send
    setMessage("");
    onClose();
  }

  if (!isOpen) return null;

  return (
    // overlay
    <div
      aria-modal="true"
      role="dialog"
      className="fixed inset-0 z-50 flex items-center justify-center px-4"
    >
      {/* dim background */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* modal card */}
      <div
        className="relative z-10 w-full max-w-4xl rounded-2xl bg-white shadow-[0_30px_60px_rgba(0,0,0,0.45)] border border-transparent"
        style={{ minHeight: "360px" }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between p-6 border-b border-gray-100 rounded-t-2xl">
          <div>
            <h3 className="text-lg font-semibold text-gray-800">
              Contact {candidateName}
            </h3>
            <p className="mt-1 text-sm text-gray-500">
              Reach out to the candidate to schedule the call.
            </p>
          </div>

          {/* Close button */}
          <button
            onClick={onClose}
            aria-label="Close dialog"
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
              aria-hidden
            >
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        {/* Body */}
        <div className="px-8 py-6">
          {/* Tabs (WhatsApp / Email) */}
          <div className="mb-6">
            <nav className="flex items-center gap-6 border-b border-gray-100 pb-3">
              <button
                onClick={() => setActiveTab("whatsapp")}
                className={`text-sm font-medium ${
                  activeTab === "whatsapp"
                    ? "text-[#075E54] border-b-2 border-[#075E54] pb-1"
                    : "text-gray-500"
                }`}
              >
                WhatsApp
              </button>
              <button
                onClick={() => setActiveTab("email")}
                className={`text-sm font-medium ${
                  activeTab === "email"
                    ? "text-[#0B7285] border-b-2 border-[#0B7285] pb-1"
                    : "text-gray-500"
                }`}
              >
                Email
              </button>
            </nav>
          </div>

          {/* Message label */}
          <label className="block text-sm font-normal text-gray-700 mb-3">
            Message
          </label>

          {/* Textarea */}
          <textarea
            ref={textareaRef}
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder={
              activeTab === "whatsapp"
                ? `Hi ${candidateName},\n\nHope you're well — we'd like to schedule a quick call to discuss an opportunity. Are you available this week? Please share your available slots.`
                : `Hello ${candidateName},\n\nI'm reaching out to schedule a short call to discuss a role that may interest you. Please let me know your availability.`
            }
            className="w-full resize-none rounded-lg border border-[#E6F0F0] bg-[#FAFEFE] px-4 py-4 text-sm leading-6 text-gray-700 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-[#D6EEF0] focus:border-transparent shadow-sm"
            rows={8}
          />
        </div>

        {/* Footer: Actions */}
        <div className="flex items-center justify-end gap-4 px-8 py-5 border-t border-gray-100">
          <button
            onClick={() => {
              setMessage(initialMessage);
              onClose();
            }}
            className="inline-flex items-center justify-center rounded-md border border-transparent bg-[#F2F2F2] px-4 py-2 text-sm font-medium text-gray-700 hover:brightness-95 focus:outline-none focus:ring-2 focus:ring-gray-200"
          >
            Cancel
          </button>

          <button
            onClick={handleSend}
            className="inline-flex items-center justify-center rounded-md bg-[#007BFF] px-5 py-2 text-sm font-semibold text-white shadow-sm hover:brightness-95 active:scale-[0.995] focus:outline-none focus:ring-2 focus:ring-[#B3D4FF]"
          >
            Send
          </button>
        </div>
      </div>
    </div>
  );
}
