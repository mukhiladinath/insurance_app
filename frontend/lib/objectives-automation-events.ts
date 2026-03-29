/**
 * Browser events + copy for the goals → automated insurance analysis workflow.
 * FactFind, orchestrator extract handler, and ObjectivesAutomationStatus use these.
 */

import type { ObjectivesAutomationResult } from './api';

export const OA_EVENT_START = 'objectives-automation-start';
export const OA_EVENT_DONE = 'objectives-automation-done';

export function dispatchObjectivesAutomationStart(clientId: string): void {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new CustomEvent(OA_EVENT_START, { detail: { clientId } }));
}

export function dispatchObjectivesAutomationDone(
  clientId: string,
  result: ObjectivesAutomationResult,
): void {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new CustomEvent(OA_EVENT_DONE, { detail: { clientId, result } }));
}

/** Registry tool_id → short label for advisers */
export const REGISTRY_TOOL_LABELS: Record<string, string> = {
  purchase_retain_life_tpd_policy: 'Life & TPD (retail)',
  purchase_retain_life_insurance_in_super: 'Life insurance in super',
  purchase_retain_income_protection_policy: 'Income protection',
  purchase_retain_ip_in_super: 'IP in super',
  tpd_policy_assessment: 'TPD assessment',
  purchase_retain_trauma_ci_policy: 'Trauma / critical illness',
  purchase_retain_tpd_in_super: 'TPD in super',
};

export function registryToolLabel(id: string): string {
  return REGISTRY_TOOL_LABELS[id] ?? id.replace(/_/g, ' ');
}

export type AutomationCopyTone = 'success' | 'warning' | 'info';

export function describeAutomationResult(r: ObjectivesAutomationResult): {
  tone: AutomationCopyTone;
  title: string;
  lines: string[];
} {
  if (r.skipped) {
    if (r.reason.toLowerCase().includes('unchanged')) {
      return {
        tone: 'info',
        title: 'Automated analysis not re-run',
        lines: [
          'Your Goals & objectives text is unchanged since the last automated run, so engines were skipped.',
          'Change the text and save again to run a new analysis.',
        ],
      };
    }
    if (r.reason.toLowerCase().includes('empty')) {
      return {
        tone: 'info',
        title: 'No goals text',
        lines: [r.reason],
      };
    }
    return {
      tone: 'info',
      title: 'Skipped',
      lines: [r.reason || 'No action taken.'],
    };
  }

  if (r.tools_run.length === 0) {
    return {
      tone: 'warning',
      title: 'No insurance tools selected',
      lines: [
        r.reason ||
          'The selector did not match any of the seven engines. Try naming cover types (e.g. income protection, trauma, TPD in super, life in super).',
      ],
    };
  }

  if (r.outputs_created > 0) {
    const ran = r.tools_run.map((id) => registryToolLabel(id)).join(' · ');
    const lines = [
      `Steps completed: ${ran}.`,
      'A merged summary is in Saved analyses (look for the Automated tag).',
    ];
    if (r.insurance_dashboard_created && r.insurance_dashboard_id) {
      lines.push('An insurance projection dashboard was created — open the Dashboards tab to review.');
    }
    return {
      tone: 'success',
      title: 'Automated analysis finished',
      lines,
    };
  }

  return {
    tone: 'warning',
    title: 'Analysis finished with nothing saved',
    lines: [r.reason || 'Check fact find data and try again.'],
  };
}
