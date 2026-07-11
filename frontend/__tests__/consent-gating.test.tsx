/**
 * Safety requirement #6/#7: recording UI must never be shown before
 * explicit consent, and the consent page must never call the consent
 * endpoint without an explicit user click. Consent and recording now live
 * on the same page/component (no route navigation between them), so this
 * verifies the phase gating within that single component instead of a
 * redirect between pages.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ParticipantPage from "@/app/participant/[participantToken]/page";

jest.mock("next/navigation", () => ({
  useParams: () => ({ participantToken: "tok-123" }),
}));

const grantConsentMock = jest.fn().mockResolvedValue({});

jest.mock("@/lib/api", () => ({
  api: {
    getParticipantByToken: jest.fn(),
    grantConsent: (...args: unknown[]) => grantConsentMock(...args),
    revokeConsent: jest.fn(),
    deleteAudioSample: jest.fn(),
  },
  ApiError: class ApiError extends Error {},
}));

const { api } = jest.requireMock("@/lib/api");

describe("Consent gating on the merged participant page", () => {
  it("does not show recording UI before consent is granted", async () => {
    api.getParticipantByToken.mockResolvedValueOnce({
      id: "p1",
      session_id: "s1",
      display_name: "Alex",
      consent_status: "none",
      has_audio_sample: false,
      session_is_active: true,
    });

    render(<ParticipantPage />);

    await screen.findByText(/I consent to this voice sample being recorded/i);
    expect(screen.queryByText(/Start continuous recording/i)).not.toBeInTheDocument();
  });

  it("does not call grantConsent until the consent button is pressed, then reveals recording UI", async () => {
    api.getParticipantByToken.mockResolvedValueOnce({
      id: "p1",
      session_id: "s1",
      display_name: "Alex",
      consent_status: "none",
      has_audio_sample: false,
      session_is_active: true,
    });

    render(<ParticipantPage />);

    const button = await screen.findByText(/I consent to this voice sample being recorded/i);
    expect(grantConsentMock).not.toHaveBeenCalled();

    await userEvent.click(button);
    expect(grantConsentMock).toHaveBeenCalledWith("p1");

    await waitFor(() => expect(screen.getByText(/Start continuous recording/i)).toBeInTheDocument());
  });
});
