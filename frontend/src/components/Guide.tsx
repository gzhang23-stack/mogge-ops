"use client";

import { useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";

export interface GuideStep {
  title: string;
  body: string;
}

export function Guide({ title, steps }: { title: string; steps: GuideStep[] }) {
  const [open, setOpen] = useState(false);

  return (
    <section className="panel guide-panel">
      <button className="guide-toggle" onClick={() => setOpen((value) => !value)}>
        <span>{title}</span>
        {open ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
      </button>
      {open ? (
        <div className="guide-content">
          {steps.map((step, index) => (
            <div className="guide-step" key={step.title}>
              <strong>{index + 1}. {step.title}</strong>
              <p>{step.body}</p>
            </div>
          ))}
        </div>
      ) : null}
    </section>
  );
}

