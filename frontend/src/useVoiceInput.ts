import { useEffect, useRef, useState } from "react";

/**
 * Browser-native voice input via the Web Speech API — no backend key, no
 * server round trip, nothing to configure. Feature-detected: `supported` is
 * false on browsers without it (e.g. desktop Firefox), so the caller can hide
 * the mic entirely rather than show a button that would just fail.
 *
 * Mirrors the same slice of "voice experience" already shipped in the
 * IP Sakti Sahayak website prototype: single-utterance recognition, a two-way
 * language toggle (English / Hindi), and the transcript appended to whatever
 * the user already typed rather than replacing it.
 */

type SpeechLang = "en-IN" | "hi-IN";

interface UseVoiceInput {
  supported: boolean;
  listening: boolean;
  lang: SpeechLang;
  toggleLang: () => void;
  toggleListening: () => void;
}

export function useVoiceInput(onResult: (transcript: string) => void): UseVoiceInput {
  const [supported, setSupported] = useState(false);
  const [listening, setListening] = useState(false);
  const [lang, setLang] = useState<SpeechLang>("en-IN");
  const recognitionRef = useRef<any>(null);
  const onResultRef = useRef(onResult);
  onResultRef.current = onResult;

  useEffect(() => {
    const Ctor =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!Ctor) return; // no support: leave the mic hidden

    const recognition = new Ctor();
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = "en-IN";

    recognition.addEventListener("start", () => setListening(true));
    recognition.addEventListener("end", () => setListening(false));
    recognition.addEventListener("error", () => setListening(false));
    recognition.addEventListener("result", (event: any) => {
      const transcript = event.results?.[0]?.[0]?.transcript;
      if (transcript) onResultRef.current(transcript);
    });

    recognitionRef.current = recognition;
    setSupported(true);

    return () => {
      recognition.abort();
    };
  }, []);

  function toggleLang() {
    setLang((prev) => {
      const next: SpeechLang = prev === "en-IN" ? "hi-IN" : "en-IN";
      if (recognitionRef.current) recognitionRef.current.lang = next;
      return next;
    });
  }

  function toggleListening() {
    const recognition = recognitionRef.current;
    if (!recognition) return;
    if (listening) {
      recognition.stop();
      return;
    }
    try {
      recognition.lang = lang;
      recognition.start();
    } catch {
      // A second start() while already active throws — safe to ignore, the
      // existing session just keeps running.
    }
  }

  return { supported, listening, lang, toggleLang, toggleListening };
}
