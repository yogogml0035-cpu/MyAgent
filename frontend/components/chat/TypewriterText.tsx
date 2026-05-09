"use client";

import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

type TypewriterTextProps = {
  text: string;
  speed?: number;
  onComplete?: () => void;
  enableMarkdown?: boolean;
};

export function TypewriterText({
  text,
  speed = 12,
  onComplete,
  enableMarkdown = true,
}: TypewriterTextProps) {
  const [displayedText, setDisplayedText] = useState("");
  const [currentIndex, setCurrentIndex] = useState(0);

  useEffect(() => {
    if (currentIndex < text.length) {
      const timeout = setTimeout(() => {
        const nextIndex = Math.min(currentIndex + speed, text.length);
        setDisplayedText(text.slice(0, nextIndex));
        setCurrentIndex(nextIndex);
      }, 16);
      return () => clearTimeout(timeout);
    } else if (onComplete && currentIndex > 0 && currentIndex === text.length) {
      onComplete();
    }
  }, [currentIndex, text, speed, onComplete]);

  useEffect(() => {
    if (text.length > displayedText.length) {
      const timeout = setTimeout(() => {
        const nextIndex = Math.min(currentIndex + speed, text.length);
        setDisplayedText(text.slice(0, nextIndex));
        setCurrentIndex(nextIndex);
      }, 16);
      return () => clearTimeout(timeout);
    }
  }, [text, displayedText.length, currentIndex, speed]);

  if (enableMarkdown) {
    return (
      <div className="typewriter-text">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{displayedText}</ReactMarkdown>
      </div>
    );
  }

  return <span className="typewriter-text">{displayedText}</span>;
}
