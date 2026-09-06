import type { Session } from "../useSessions";
import { relativeDay, titleFor } from "../useSessions";
import type { UiLang } from "../i18n";

interface Props {
  sessions: Session[];
  activeId: string;
  lang: UiLang;
  labels: {
    newConsultation: string;
    consultations: string;
    questionsCount: string;
    questionCount: string;
    untitledSession: string;
    deleteSession: string;
  };
  onNew: () => void;
  onOpen: (id: string) => void;
  onRemove: (id: string) => void;
}

/**
 * Past consultations, newest first.
 *
 * Deliberately not styled as a chat list. The identity here is a printed legal
 * opinion sheet (CLAUDE.md 6e), so this reads as an index of filed matters: a
 * ruled list, a haldi rule marking the open one - the same marker the reasoning
 * trail uses for the current step - and no avatars, bubbles or timestamps to
 * the minute.
 */
export function SessionList({
  sessions,
  activeId,
  lang,
  labels,
  onNew,
  onOpen,
  onRemove,
}: Props) {
  const withContent = sessions.filter((s) => s.turns.length > 0);

  return (
    <div className="pb-4">
      <button
        type="button"
        onClick={onNew}
        className="group flex w-full items-center gap-2 rounded-[3px] border border-haldi/40 bg-haldi/10 px-3 py-2.5 text-left text-[12.5px] font-medium text-paper transition-colors hover:border-haldi/70 hover:bg-haldi/20"
      >
        <span className="font-serif text-[15px] leading-none text-haldi">+</span>
        <span>{labels.newConsultation}</span>
      </button>

      {withContent.length > 0 && (
        <>
          <div className="mb-1.5 mt-5 flex items-baseline justify-between">
            <span className="eyebrow text-paper/45">{labels.consultations}</span>
            <span className="text-[11px] tabular-nums text-paper/35">{withContent.length}</span>
          </div>

          <ul className="-mx-1 max-h-[34vh] overflow-y-auto">
            {withContent.map((session) => {
              const isActive = session.id === activeId;
              const count = session.turns.length;
              return (
                <li key={session.id} className="group/item relative">
                  <button
                    type="button"
                    onClick={() => onOpen(session.id)}
                    aria-current={isActive ? "true" : undefined}
                    className={`flex w-full flex-col items-start gap-0.5 border-l-2 py-2 pl-2.5 pr-7 text-left transition-colors ${
                      isActive
                        ? "border-haldi bg-white/[0.06]"
                        : "border-transparent hover:border-paper/25 hover:bg-white/[0.03]"
                    }`}
                  >
                    <span
                      className={`line-clamp-2 text-[12.5px] leading-snug ${
                        isActive ? "text-paper" : "text-paper/70"
                      }`}
                    >
                      {titleFor(session) || labels.untitledSession}
                    </span>
                    <span className="text-[11px] tabular-nums text-paper/35">
                      {count} {count === 1 ? labels.questionCount : labels.questionsCount} ·{" "}
                      {relativeDay(session.updatedAt, lang)}
                    </span>
                  </button>

                  {/* Hover-only, matching the per-turn remove in the transcript.
                      Always-visible delete controls invite the misclick. */}
                  <button
                    type="button"
                    aria-label={labels.deleteSession}
                    title={labels.deleteSession}
                    onClick={(event) => {
                      event.stopPropagation();
                      onRemove(session.id);
                    }}
                    className="absolute right-1 top-2 rounded-[2px] px-1.5 py-0.5 text-[12px] leading-none text-paper/30 opacity-0 transition-opacity hover:bg-clay/25 hover:text-paper/80 focus:opacity-100 group-hover/item:opacity-100"
                  >
                    ✕
                  </button>
                </li>
              );
            })}
          </ul>
        </>
      )}
    </div>
  );
}
