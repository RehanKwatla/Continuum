import { describe, expect, it, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ThemeProvider, useTheme } from "@/contexts/ThemeContext";
import { ThemeToggle } from "@/components/common/ThemeToggle";

function TestConsumer() {
  const { theme, toggleTheme } = useTheme();
  return (
    <div>
      <span data-testid="current-theme">{theme}</span>
      <button onClick={toggleTheme}>Toggle</button>
    </div>
  );
}

describe("ThemeContext & ThemeToggle", () => {
  beforeEach(() => {
    window.localStorage.clear();
    document.documentElement.className = "";
  });

  it("provides dark theme by default and toggles to light", async () => {
    const user = userEvent.setup();
    render(
      <ThemeProvider>
        <TestConsumer />
      </ThemeProvider>,
    );

    expect(screen.getByTestId("current-theme")).toHaveTextContent("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);

    await user.click(screen.getByText("Toggle"));

    expect(screen.getByTestId("current-theme")).toHaveTextContent("light");
    expect(document.documentElement.classList.contains("light")).toBe(true);
    expect(document.documentElement.classList.contains("dark")).toBe(false);
    expect(window.localStorage.getItem("continuum.theme")).toBe("light");
  });

  it("renders ThemeToggle switch and switches on click", async () => {
    const user = userEvent.setup();
    render(
      <ThemeProvider>
        <ThemeToggle showLabel />
      </ThemeProvider>,
    );

    const toggle = screen.getByRole("switch");
    expect(toggle).toHaveAttribute("aria-checked", "true");
    expect(screen.getByText("Dark theme")).toBeInTheDocument();

    await user.click(toggle);

    expect(toggle).toHaveAttribute("aria-checked", "false");
    expect(screen.getByText("Light theme")).toBeInTheDocument();
    expect(document.documentElement.classList.contains("light")).toBe(true);

    await user.click(toggle);

    expect(toggle).toHaveAttribute("aria-checked", "true");
    expect(screen.getByText("Dark theme")).toBeInTheDocument();
    expect(document.documentElement.classList.contains("dark")).toBe(true);
  });
});

