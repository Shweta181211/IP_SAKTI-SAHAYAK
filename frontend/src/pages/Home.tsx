import { useState } from "react";
import { Link } from "react-router-dom";
import { useShell } from "../Shell";


const BLOOMS = [
  {
    id: "classical",
    en: "Classical",
    hi: "शास्त्रीय",
    tease: "Formulations drawn from a First Schedule text. Ask what protection is available — the answer names the provision it rests on.",
    teaseHi: "प्रथम अनुसूची ग्रंथ से ली गई संरचनाएँ। पूछिए कि कौन सा संरक्षण उपलब्ध है — उत्तर अपना प्रावधान नामित करता है।",
    q: "Can a classical churna from a First Schedule text be patented?",
  },
  {
    id: "proprietary",
    en: "Proprietary",
    hi: "स्वामित्व",
    tease: "A formulation of the manufacturer’s own composition. Ask how that changes the route, and read the provision behind the answer.",
    teaseHi: "निर्माता की स्वयं की संरचना। पूछिए कि इससे मार्ग कैसे बदलता है।",
    q: "Is my new herbal extract formulation patentable?",
  },
  {
    id: "phyto",
    en: "Phyto",
    hi: "फाइटो",
    tease: "A standardised plant fraction with defined markers. Ask what evidence the rules call for, and see it cited.",
    teaseHi: "निर्धारित चिह्नकों वाला मानकीकृत अंश। पूछिए कि नियम कौन सा साक्ष्य चाहते हैं।",
    q: "What counts as a phytopharmaceutical under Indian law?",
  },
  {
    id: "abs",
    en: "ABS",
    hi: "ABS",
    tease: "Access and benefit sharing. Ask when the National Biodiversity Authority is engaged, and the answer cites what says so.",
    teaseHi: "पहुँच और लाभ-साझाकरण। पूछिए कि राष्ट्रीय जैव विविधता प्राधिकरण कब संबद्ध होता है।",
    q: "What is Access and Benefit Sharing and when do I need NBA approval?",
  },
  {
    id: "gi",
    en: "GI",
    hi: "GI",
    tease: "Origin-based protection for goods tied to a place. Ask whether a geographical indication fits your product.",
    teaseHi: "स्थान से जुड़े सामान का संरक्षण। पूछिए कि भौगोलिक संकेत आपके उत्पाद पर लागू होता है या नहीं।",
    q: "How do I register a Geographical Indication for an Ayurvedic product?",
  },
  {
    id: "treaty",
    en: "Treaties",
    hi: "संधियाँ",
    tease: "PCT, Madrid and Nagoya sit in a separate corpus and are not retrieved with Indian statutes.",
    teaseHi: "PCT, मैड्रिड और नागोया अलग कॉर्पस में हैं; भारतीय क़ानूनों के साथ नहीं मिलाए जाते।",
    q: "What does the Nagoya Protocol require for access to genetic resources?",
  },
];

export function Home() {
  const { uiLang } = useShell();
  const hi = uiLang === "hi";
  const [bloom, setBloom] = useState<(typeof BLOOMS)[number] | null>(BLOOMS[0]);

  return (
    <div className="explore">
      {/* ---------- HERO ---------- */}
      <section className="explore-hero">
        <div className="explore-hero-copy">
          <h1 className="explore-title">
            {hi
              ? "प्रत्येक दावा उद्धृत प्रावधान पर टिके, अनुमान पर नहीं।"
              : "Every claim rests on a cited provision, never on a guess."}
          </h1>
          <p className="explore-lead">
            {hi
              ? "आयुर्वेद के लिए स्रोत-उद्धृत आईपी व नियामक सहायक। निर्माण श्रेणी प्रश्न से निर्धारित होती है; क्षेत्राधिकार आप चुनते हैं, और दोनों कॉरपस अलग-अलग खोजे जाते हैं।"
              : "A source-cited assistant for intellectual property and regulatory questions in Ayurveda. The formulation category is read from your question, the jurisdiction is yours to choose, and the two corpora are searched separately."}
          </p>
          <div className="explore-cta-row">
            <Magnetic to="/ask">{hi ? "परामर्श शुरू करें" : "Begin consultation"}</Magnetic>
            <a href="#garden" className="explore-ghost">
              {hi ? "श्रेणियाँ देखें" : "Review the categories"}
            </a>
          </div>
          {/* The number this audience actually weighs, stated as a fact rather
              than dressed up as a badge. */}
          <p className="explore-corpus">
            {hi ? (
              <>
                <b>3,275</b> प्रावधान अनुक्रमित · <b>37</b> दस्तावेज़ · भारतीय और
                अंतरराष्ट्रीय कॉर्पस अलग-अलग
              </>
            ) : (
              <>
                <b>3,275</b> provisions indexed across <b>37</b> instruments, in two
                corpora that are searched apart.
              </>
            )}
          </p>
        </div>

        <svg className="explore-mark" viewBox="0 0 200 240" aria-hidden>
          <ellipse cx="100" cy="128" rx="54" ry="78" fill="none" stroke="currentColor" strokeWidth="1.1" />
          <path d="M100 28 C70 88 70 148 100 212 C130 148 130 88 100 28 Z" fill="currentColor" />
          <path d="M100 28 V212" fill="none" stroke="#101a14" strokeWidth="1" opacity="0.35" />
        </svg>
      </section>

      {/* ---------- GARDEN ---------- */}
      <section id="garden" className="explore-garden">
        <div className="explore-garden-copy">
          <p className="explore-kicker explore-kicker--ink">
            {hi ? "परिचय · चयन नहीं" : "Orientation · not a filing step"}
          </p>
          <h2>
            {hi ? "छह नियामक श्रेणियाँ।" : "Six regulatory categories."}
          </h2>
          <p>
            {hi
              ? "शास्त्रीय, स्वामित्व, नई औषधि, फाइटोफार्मास्युटिकल, आयुर्वेद आहार, और संधि व्यवस्था। होवर कर विवरण देखें। प्रश्न भेजते समय ये बटन नहीं हैं — सहायक स्वयं वर्गीकृत करता है।"
              : "Classical, proprietary, new drug, phytopharmaceutical, Ayurveda Aahar, and treaty instruments. Hover to read a brief. Nothing here is a form field — the assistant classifies the formulation from the question itself."}
          </p>
          {bloom && (
            <div className="explore-bloom-card" key={bloom.id}>
              <p className="explore-kicker explore-kicker--ink">{hi ? bloom.hi : bloom.en}</p>
              <p className="explore-bloom-text">{hi ? bloom.teaseHi : bloom.tease}</p>
              <Link to={`/ask?q=${encodeURIComponent(bloom.q)}`} className="explore-bloom-link">
                {hi ? "इस प्रश्न से परामर्श करें →" : "Consult on this question →"}
              </Link>
            </div>
          )}
        </div>
        <div className="explore-orbit">
          {BLOOMS.map((b, i) => {
            const angle = -90 + i * 60;
            return (
              <button
                key={b.id}
                type="button"
                className={`explore-leaf ${bloom?.id === b.id ? "is-open" : ""}`}
                style={{ "--a": `${angle}deg` } as React.CSSProperties}
                onMouseEnter={() => setBloom(b)}
                onFocus={() => setBloom(b)}
                onClick={() => setBloom(b)}
              >
                <span>{hi ? b.hi : b.en}</span>
              </button>
            );
          })}
          <div className="explore-orbit-core" aria-hidden>
            <span>IP</span>
          </div>
        </div>
      </section>

      {/* ---------- TWO WORLDS ---------- */}
      <section className="explore-worlds">
        <h2>
          {hi
            ? "भारतीय क़ानून और अंतरराष्ट्रीय संधियाँ अलग अनुक्रमित हैं।"
            : "Indian statutes and international treaties are indexed separately."}
        </h2>
        <p className="explore-worlds-intro">
          {hi
            ? "एक परत चुनिए — परामर्श उसी क्षेत्राधिकार में खुलेगा।"
            : "Choose a layer and the consultation opens in that jurisdiction."}
        </p>
        {/* These were buttons that only tinted themselves on hover, which is a
            control that looks live and does nothing. They are links now: each
            opens Consult already set to its own corpus. */}
        <div className="explore-split">
          <Link to="/ask?j=india" className="explore-pane reveal-in">
            <h3>{hi ? "भारत" : "India"}</h3>
            <p>
              {hi
                ? "पेटेंट, भौगोलिक संकेत, व्यापार चिह्न, ABS, औषधि नियम और TKDL। धारा 3(p) इसी परत से प्राप्त होती है।"
                : "Patents, geographical indications, trade marks, ABS, drug rules and TKDL. Section 3(p) is retrieved from this layer."}
            </p>
            <span className="explore-pane-go">
              {hi ? "भारतीय क़ानून में पूछें" : "Ask in Indian law"}
            </span>
          </Link>
          <Link
            to="/ask?j=international"
            className="explore-pane explore-pane--clay reveal-in"
            style={{ ["--i" as string]: 1 }}
          >
            <h3>{hi ? "अंतरराष्ट्रीय" : "International"}</h3>
            <p>
              {hi
                ? "TRIPS, नागोया, PCT, मैड्रिड, हेग, बुडापेस्ट और GRATK। अलग कॉर्पस, ताकि भारतीय क़ानून से मिश्रित न हों।"
                : "TRIPS, Nagoya, PCT, Madrid, Hague, Budapest and GRATK. Held in a separate corpus so they are never mixed with Indian law."}
            </p>
            <span className="explore-pane-go">
              {hi ? "संधि पाठ में पूछें" : "Ask in the treaty texts"}
            </span>
          </Link>
        </div>
        <p className="explore-worlds-note">
          {hi
            ? "भारत डिफ़ॉल्ट है। इस कॉर्पस में FDA या EMA के पाठ नहीं हैं; विदेशी घरेलू प्राधिकार के प्रश्न भारतीय क़ानून से उत्तर देने के बजाय अस्वीकार किए जाते हैं।"
            : "India is the default. This corpus holds no FDA or EMA text, so questions on foreign domestic authorisation are declined rather than answered from Indian law."}
        </p>
      </section>

      {/* ---------- DIVE ---------- */}
      <section className="explore-dive">
        <h2>{hi ? "प्रश्न दर्ज करें।" : "Submit a question."}</h2>
        <p>
          {hi
            ? "कोई श्रेणी फ़ॉर्म नहीं। वर्गीकरण, पुनर्प्राप्ति और उद्धरण जाँच स्वतः चलती है।"
            : "There is no category form. Classification, retrieval and citation checks run automatically."}
        </p>
        <Magnetic to="/ask">{hi ? "परामर्श शुरू करें" : "Begin consultation"}</Magnetic>
      </section>
    </div>
  );
}

function Magnetic({ to, children }: { to: string; children: string }) {
  const [t, setT] = useState({ x: 0, y: 0 });
  return (
    <Link
      to={to}
      className="explore-magnetic"
      onMouseMove={(e) => {
        const r = e.currentTarget.getBoundingClientRect();
        setT({
          x: (e.clientX - (r.left + r.width / 2)) * 0.22,
          y: (e.clientY - (r.top + r.height / 2)) * 0.22,
        });
      }}
      onMouseLeave={() => setT({ x: 0, y: 0 })}
      style={{ transform: `translate(${t.x}px, ${t.y}px)` }}
    >
      {children}
    </Link>
  );
}
