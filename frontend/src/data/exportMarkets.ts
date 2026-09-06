/** Treaty lanes for the Export page. Questions hit the international corpus. */

export interface ExportLane {
  id: string;
  treaty: string;
  file: string;
  use: string;
  question: string;
}

export const EXPORT_LANES: ExportLane[] = [
  {
    id: "pct",
    treaty: "Patent Cooperation Treaty",
    file: "05_WIPO_PCT_and_Regulations_2026.pdf",
    use: "One international patent filing, then national phase in chosen countries.",
    question:
      "What does the Patent Cooperation Treaty provide for filing a patent application covering several countries?",
  },
  {
    id: "epc",
    treaty: "European Patent Convention",
    file: "09_EPO_European_Patent_Convention.pdf",
    use: "Grant of a European patent covering designated EPC contracting states.",
    question:
      "What does the European Patent Convention provide for obtaining a patent covering several European states?",
  },
  {
    id: "thmpd",
    treaty: "EU Directive 2004/24/EC",
    file: "10_EU_Directive_2004_24_Traditional_Herbal_Medicinal_Products.pdf",
    use: "Traditional herbal medicinal product registration in the European Union.",
    question:
      "What does EU Directive 2004/24/EC require for a traditional herbal medicinal product?",
  },
  {
    id: "madrid",
    treaty: "Madrid Protocol",
    file: "06_WIPO_Madrid_Protocol_Rules_2025.pdf",
    use: "International trade-mark registration from a single application.",
    question:
      "How does the Madrid Protocol let me seek trade-mark protection in several countries from one filing?",
  },
  {
    id: "hague",
    treaty: "Hague Agreement (Geneva Act)",
    file: "07_WIPO_Hague_Agreement_Geneva_Act.pdf",
    use: "International industrial-design registration for packaging and product form.",
    question:
      "What does the Hague Agreement Geneva Act provide for registering an industrial design internationally?",
  },
  {
    id: "budapest",
    treaty: "Budapest Treaty",
    file: "08_WIPO_Budapest_Treaty.pdf",
    use: "Deposit of a micro-organism to support a patent in multiple offices.",
    question:
      "What does the Budapest Treaty require for depositing a micro-organism in support of a patent?",
  },
  {
    id: "trips",
    treaty: "WTO TRIPS Agreement",
    file: "01_WTO_TRIPS_Agreement.pdf",
    use: "Minimum IP standards WTO members must meet, including patents and undisclosed information.",
    question:
      "What does the TRIPS Agreement say about patentable subject matter and traditional knowledge related inventions?",
  },
  {
    id: "cbd",
    treaty: "Convention on Biological Diversity",
    file: "02_CBD_Convention_on_Biological_Diversity.pdf",
    use: "Sovereign rights over genetic resources; the frame for access when material leaves India.",
    question:
      "What does the Convention on Biological Diversity say about sovereign rights over genetic resources and access?",
  },
  {
    id: "nagoya",
    treaty: "Nagoya Protocol",
    file: "03_CBD_Nagoya_Protocol.pdf",
    use: "Access and benefit-sharing when genetic resources or associated TK are used abroad.",
    question:
      "What does the Nagoya Protocol require for access to genetic resources and associated traditional knowledge?",
  },
  {
    id: "gratk",
    treaty: "WIPO GRATK Treaty 2024",
    file: "04_WIPO_GRATK_Treaty_2024.pdf",
    use: "Disclosure of genetic resources and associated TK in patent applications.",
    question:
      "What disclosure does the WIPO GRATK Treaty 2024 require in patent applications involving genetic resources or traditional knowledge?",
  },
];

export const OFFICIAL_SOURCES = [
  {
    name: "Traditional Knowledge Digital Library",
    href: "https://www.tkdl.res.in",
    note: "Defensive prior-art archive for Indian traditional knowledge.",
  },
  {
    name: "India Code",
    href: "https://www.indiacode.nic.in",
    note: "Official text of Central Acts.",
  },
  {
    name: "IP India",
    href: "https://www.ipindia.gov.in",
    note: "Patents, trade marks, designs and GI public databases and forms.",
  },
  {
    name: "National Biodiversity Authority",
    href: "https://nbaindia.org",
    note: "ABS approvals and Form-I / Form-B guidance.",
  },
  {
    name: "WIPO",
    href: "https://www.wipo.int",
    note: "PCT, Madrid, Hague, Budapest and GRATK treaty texts and filing portals.",
  },
  {
    name: "Convention on Biological Diversity",
    href: "https://www.cbd.int",
    note: "CBD and Nagoya Protocol, including the ABS Clearing-House.",
  },
];
