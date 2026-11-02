"use strict";
/* Daily quiz tab: the same five decisions all day, answers are final. */

const QUIZ = { data: null, current: 0, justAnswered: null };

function renderQuiz() {
  const q = QUIZ.data, head = PL.$("#quiz-head"), body = PL.$("#quiz-body");
  const dots = PL.el("div", { className: "dots" }, q.questions.map((x, i) => {
    const d = PL.el("button", { className: `dot ${x.answered ? x.result?.verdict || "done" : ""} ${i === QUIZ.current ? "cur" : ""}`, title: `Question ${i + 1}` }, String(i + 1));
    d.addEventListener("click", () => { QUIZ.current = i; QUIZ.justAnswered = null; renderQuiz(); });
    return d;
  }));
  head.replaceChildren(
    PL.el("div", { className: "controls" },
      PL.el("strong", {}, `Daily quiz · ${q.day}`),
      PL.el("span", { className: "muted" }, `${q.answered}/${q.size} answered` +
        (q.avg_score != null ? ` · average score ${(q.avg_score * 100).toFixed(0)}%` : "") +
        (q.streak ? ` · ${q.streak}-day streak` : ""))),
    dots);

  const item = q.questions[QUIZ.current];
  const parts = [];
  if (QUIZ.justAnswered && QUIZ.justAnswered.idx === item.idx) parts.push(PL.feedbackView(QUIZ.justAnswered.fb));
  else if (item.answered && item.result) parts.push(PL.feedbackView(item.result));
  if (item.state) parts.push(PL.decisionView(item.state, (a) => answer(item.idx, a), item.answered));
  else parts.push(PL.el("p", { className: "muted" }, "The solve behind this question was deleted."));
  const nextIdx = q.questions.findIndex((x, i) => i > QUIZ.current && !x.answered);
  if (item.answered && nextIdx >= 0) {
    const b = PL.el("button", {}, "Next question");
    b.addEventListener("click", () => { QUIZ.current = nextIdx; QUIZ.justAnswered = null; renderQuiz(); });
    parts.push(b);
  }
  if (q.complete) parts.push(PL.el("p", { className: "done-banner" },
    `All done for today. Score ${(q.avg_score * 100).toFixed(0)}%.` + (q.streak ? ` ${q.streak}-day streak.` : "")));
  body.replaceChildren(...parts);
}

async function answer(idx, action) {
  PL.$("#quiz-error").textContent = "";
  try {
    const out = await PL.post(`/api/quiz/today/${idx}/answer`, { action });
    QUIZ.data = out.progress;
    QUIZ.justAnswered = { idx, fb: out.feedback };
    renderQuiz();
  } catch (e) {
    PL.$("#quiz-error").textContent = e.message;
  }
}

async function loadQuiz() {
  PL.$("#quiz-error").textContent = "";
  try {
    QUIZ.data = await PL.api("/api/quiz/today");
    if (QUIZ.data.questions[QUIZ.current]?.answered) {
      const firstOpen = QUIZ.data.questions.findIndex((x) => !x.answered);
      if (firstOpen >= 0 && !QUIZ.justAnswered) QUIZ.current = firstOpen;
    }
    renderQuiz();
  } catch (e) {
    PL.$("#quiz-head").replaceChildren();
    PL.$("#quiz-body").replaceChildren();
    PL.$("#quiz-error").textContent = e.message;
  }
}

PL.hooks.quiz = loadQuiz;
