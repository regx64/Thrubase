import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { CheckpointCard } from '../src/climb/CheckpointCard';
import { LangProvider } from '../src/i18n';

const options = [{ id: 'a', label: 'Engine.run' }, { id: 'b', label: 'validate' }];

describe('CheckpointCard', () => {
  it('idle: keys pick, check and skip', () => {
    const onSelect = vi.fn();
    const onSubmit = vi.fn();
    const onSkip = vi.fn();
    const { container, rerender } = render(
      <CheckpointCard type="flow" prompt="Which first?" options={options} onSelect={onSelect} onSubmit={onSubmit} onSkip={onSkip} />,
    );
    const card = container.querySelector('section')!;
    fireEvent.keyDown(card, { key: '2' });
    expect(onSelect).toHaveBeenCalledWith('b');
    expect(screen.getByRole('button', { name: 'Check' })).toBeDisabled();
    rerender(<CheckpointCard type="flow" prompt="Which first?" options={options} selected="b" onSelect={onSelect} onSubmit={onSubmit} onSkip={onSkip} />);
    expect(screen.getByRole('radio', { name: /validate/ })).toHaveAttribute('aria-checked', 'true');
    fireEvent.keyDown(card, { key: 'Enter' });
    expect(onSubmit).toHaveBeenCalledTimes(1);
    fireEvent.keyDown(card, { key: 's' });
    expect(onSkip).toHaveBeenCalledTimes(1);
  });

  it('hint: marks the wrong option and keeps the answer hidden', () => {
    render(<CheckpointCard type="flow" prompt="Which first?" options={options} state="hint" wrong="b" hint="Look again at lines 3–9." />);
    expect(screen.getByText('Look again at lines 3–9.')).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: /validate/ }).className).toContain('tb-option-wrong');
    expect(document.querySelector('.tb-option-correct')).toBeNull();
  });

  it('passed: correct option gets pass + check and Continue is focused', () => {
    const onContinue = vi.fn();
    render(<CheckpointCard type="flow" prompt="Which first?" options={options} state="passed" answer="a" explanation="Because." onContinue={onContinue} />);
    expect(screen.getByText('Passed')).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: /Engine.run/ }).className).toContain('tb-option-correct');
    expect(screen.getByRole('button', { name: 'Continue' })).toHaveFocus();
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));
    expect(onContinue).toHaveBeenCalled();
  });

  it('revealed: answer, explanation and an Unsure badge', () => {
    render(<CheckpointCard type="flow" prompt="Which first?" options={options} state="revealed" answer="a" explanation="Engine.run is called on line 30." />);
    expect(screen.getByText('Unsure')).toBeInTheDocument();
    expect(screen.getByText('Engine.run is called on line 30.')).toBeInTheDocument();
  });

  it('locate shows where to click instead of options', () => {
    const { rerender } = render(<CheckpointCard type="locate" prompt="Which line?" host="vscode" />);
    expect(screen.getByText('Click the line in the editor')).toBeInTheDocument();
    expect(screen.queryAllByRole('radio')).toHaveLength(0);
    rerender(<CheckpointCard type="locate" prompt="Which line?" host="web" />);
    expect(screen.getByText('Click a line number in the code')).toBeInTheDocument();
    rerender(<CheckpointCard type="locate" prompt="Which line?" host="web" selectedLine={42} />);
    expect(screen.getByText('Line 42')).toBeInTheDocument();
  });

  it('speaks Korean', () => {
    render(<LangProvider lang="ko"><CheckpointCard type="flow" prompt="?" options={options} /></LangProvider>);
    expect(screen.getByRole('button', { name: '확인' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '건너뛰기' })).toBeInTheDocument();
    expect(screen.getByText('흐름')).toBeInTheDocument();
  });
});
