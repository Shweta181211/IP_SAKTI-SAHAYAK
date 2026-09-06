import { useState } from "react";
import { Link } from "react-router-dom";
import { useShell } from "../Shell";
import { ACTS } from "../data/acts";


const BLOOMS = [
  {
    id: "classical",
    en: "Classical",
    hi: "शास्त्रीय",
    tease: "First Schedule formulae. Patentability is constrained by Section 3(p); TKDL is the examiner’s prior-art route.",
    teaseHi: "प्रथम अनुसूची सूत्र। पेटेंट योग्यता धारा 3(p) से सीमित है; TKDL परीक्षक का पूर्व-कला मार्ग है।",
    q: "Can a classical churna from a First Schedule text be patented?",
  },
  {
    id: "proprietary",
    en: "Proprietary",
    hi: "स्वामित्व",
    tease: "A formulation of the manufacturer’s own composition. Patentability is assessed separately from a classical text.",
    teaseHi: "निर्माता की स्वयं की संरचना। पेटेंट योग्यता शास्त्रीय पाठ से अलग आँकी जाती है।",
    q: "Is my new herbal extract formulation patentable?",
  },
  {
    id: "phyto",
    en: "Phyto",
    hi: "फाइटो",
    tease: "A standardised fraction with defined markers. Regulatory evidence requirements apply.",
    teaseHi: "निर्धारित चिह्नकों वाला मानकीकृत अंश। नियामक साक्ष्य अपेक्षाएँ लागू होती हैं।",
    q: "What counts as a phytopharmaceutical under Indian law?",
  },
  {
    id: "abs",
    en: "ABS",
    hi: "ABS",
    tease: "Prior approval of the National Biodiversity Authority is required before IPR on biological resources.",
    teaseHi: "जैव संसाधनों पर बौद्धिक संपदा से पूर्व राष्ट्रीय जैव विविधता प्राधिकरण की अनुमति आवश्यक है।",
    q: "What is Access and Benefit Sharing and when do I need NBA approval?",
  },
  {
    id: "gi",
    en: "GI",
    hi: "GI",
    tease: "Protection of origin, reputation and quality through registration — distinct from a patent.",
    teaseHi: "उत्पत्ति, प्रतिष्ठा और गुणवत्ता का पंजीकरण द्वारा संरक्षण — पेटेंट से भिन्न।",
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
  const [world, setWorld] = useState<"india" | "treaty" | null>(null);

  return (
    <div className="explore">
      {/* ---------- HERO ---------- */}
      <section className="explore-hero">
        <div className="explore-blob" aria-hidden />
        <svg className="explore-mark" viewBox="0 0 200 240" aria-hidden>
          <ellipse cx="100" cy="128" rx="54" ry="78" fill="none" stroke="currentColor" strokeWidth="1.1" />
          <path d="M100 28 C70 88 70 148 100 212 C130 148 130 88 100 28 Z" fill="currentColor" />
          <path d="M100 28 V212" fill="none" stroke="#3a1f12" strokeWidth="1" opacity="0.35" />
        </svg>

        <p className="explore-kicker">
          {hi ? "आयुर्वेद · बौद्धिक संपदा · नियामक मार्गदर्शन" : "Ayurveda · intellectual property · regulatory guidance"}
        </p>
        <h1 className="explore-title">
          {hi ? (
            <>
              प्रत्येक दावा
              <em> उद्धृत प्रावधान</em>
              <br />
              पर टिके।
            </>
          ) : (
            <>
              Every claim
              <em> rests on a cited provision,</em>
              <br />
              never on a guess.
            </>
          )}
        </h1>
        <p className="explore-lead">
          {hi
            ? "IP-SAKTI Sahayak आयुर्वेद के लिए स्रोत-उद्धृत आईपी व नियामक सहायक है। निर्माण श्रेणी प्रश्न से निर्धारित होती है; क्षेत्राधिकार आप चुनते हैं, और दोनों कॉरपस अलग-अलग खोजे जाते हैं।"
            : "IP-SAKTI Sahayak is a source-cited assistant for intellectual property and regulatory questions in Ayurveda. The formulation category is classified from your question; the jurisdiction is yours to choose, and the two corpora are searched separately."}
        </p>
        <div className="explore-cta-row">
          <Magnetic to="/ask">{hi ? "परामर्श शुरू करें" : "Begin consultation"}</Magnetic>
          <a href="#garden" className="explore-ghost">
            {hi ? "श्रेणियाँ देखें" : "Review the categories"}
          </a>
        </div>
      </section>

      {/* ---------- MARQUEE ---------- */}
      <div className="explore-marquee" aria-hidden>
        <div className="explore-marquee-track">
          {[...ACTS, ...ACTS].map((act, i) => (
            <span key={`${act}-${i}`}>{act}</span>
          ))}
        </div>
      </div>

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
        <p className="explore-kicker">{hi ? "दो परतें · मिश्रित नहीं" : "Two layers · never conflated"}</p>
        <h2>{hi ? "भारतीय क़ानून और अंतरराष्ट्रीय संधियाँ अलग अनुक्रमित हैं।" : "Indian statutes and international treaties are indexed separately."}</h2>
        <div className="explore-split">
          <button
            type="button"
            className={`explore-pane ${world === "india" ? "is-live" : ""}`}
            onMouseEnter={() => setWorld("india")}
            onFocus={() => setWorld("india")}
            onClick={() => setWorld("india")}
          >
            <span className="explore-pane-no">01</span>
            <h3>{hi ? "भारत" : "India"}</h3>
            <p>
              {hi
                ? "पेटेंट, भौगोलिक संकेत, व्यापार चिह्न, ABS, औषधि नियम और TKDL। धारा 3(p) इसी परत से प्राप्त होती है।"
                : "Patents, geographical indications, trade marks, ABS, drug rules and TKDL. Section 3(p) is retrieved from this layer."}
            </p>
          </button>
          <button
            type="button"
            className={`explore-pane explore-pane--clay ${world === "treaty" ? "is-live" : ""}`}
            onMouseEnter={() => setWorld("treaty")}
            onFocus={() => setWorld("treaty")}
            onClick={() => setWorld("treaty")}
          >
            <span className="explore-pane-no">02</span>
            <h3>{hi ? "अंतरराष्ट्रीय" : "International"}</h3>
            <p>
              {hi
                ? "TRIPS, नागोया, PCT, मैड्रिड, हेग, बुडापेस्ट और GRATK। अलग कॉर्पस, ताकि भारतीय क़ानून से मिश्रित न हों।"
                : "TRIPS, Nagoya, PCT, Madrid, Hague, Budapest and GRATK. Held in a separate corpus so they are not mixed with Indian law."}
            </p>
          </button>
        </div>
        <p className="explore-worlds-note">
          {world === "treaty"
            ? hi
              ? "भारत डिफ़ॉल्ट है। अंतरराष्ट्रीय स्थिति आपके माँगने पर ही आती है, और वह भारतीय उत्तर के साथ अलग दिखाई जाती है, मिलाई नहीं जाती।"
              : "India is the default. The international position is fetched only when you ask for it, and it is shown beside the Indian one rather than merged into it."
            : hi
              ? "इस कॉर्पस में FDA या EMA के पाठ नहीं हैं। विदेशी घरेलू प्राधिकार के प्रश्नों को भारतीय क़ानून से उत्तर देने के बजाय अस्वीकार किया जाता है।"
              : "This corpus does not include FDA or EMA texts. Questions on foreign domestic authorisation are declined rather than answered from Indian law."}
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
