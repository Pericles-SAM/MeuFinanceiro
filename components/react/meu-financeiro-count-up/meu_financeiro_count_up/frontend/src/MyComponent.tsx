import { CSSProperties, FC, ReactElement, useEffect, useRef, useState } from "react";

export type MyComponentStateShape = Record<string, unknown>;

export type MyComponentDataShape = {
  valor: number;
  rotulo: string;
  prefixo: string;
  sufixo: string;
  duracao: number;
  casas_decimais: number;
};

export type MyComponentProps = MyComponentDataShape;

const cardStyle: CSSProperties = {
  boxSizing: "border-box",
  width: "100%",
  minWidth: 0,
  padding: "18px 20px",
  border: "1px solid var(--st-border-color, rgba(99, 134, 168, 0.20))",
  borderRadius: "14px",
  background: "var(--st-secondary-background-color, #FFFFFF)",
  color: "var(--st-text-color, #293B4D)",
  fontFamily: "var(--st-font, sans-serif)",
  boxShadow: "0 3px 14px rgba(41, 59, 77, 0.045)",
};

const labelStyle: CSSProperties = {
  margin: 0,
  color: "var(--st-text-color, #718092)",
  opacity: 0.76,
  fontSize: "0.84rem",
  fontWeight: 500,
  lineHeight: 1.4,
};

const valueStyle: CSSProperties = {
  display: "flex",
  alignItems: "baseline",
  flexWrap: "wrap",
  gap: "7px",
  marginTop: "8px",
  color: "var(--st-primary-color, #6386A8)",
  fontSize: "clamp(1.55rem, 3vw, 2rem)",
  fontWeight: 700,
  letterSpacing: "-0.035em",
  lineHeight: 1.2,
  fontVariantNumeric: "tabular-nums",
  fontFeatureSettings: '"tnum"',
  overflowWrap: "anywhere",
};

const affixStyle: CSSProperties = {
  fontSize: "0.58em",
  fontWeight: 600,
  letterSpacing: "-0.01em",
  opacity: 0.9,
};

const screenReaderOnlyStyle: CSSProperties = {
  position: "absolute",
  width: 1,
  height: 1,
  padding: 0,
  margin: -1,
  overflow: "hidden",
  clip: "rect(0, 0, 0, 0)",
  whiteSpace: "nowrap",
  border: 0,
};

const MyComponent: FC<MyComponentProps> = ({
  valor,
  rotulo,
  prefixo,
  sufixo,
  duracao,
  casas_decimais,
}): ReactElement => {
  const [valorExibido, setValorExibido] = useState(0);
  const valorExibidoRef = useRef(0);

  useEffect(() => {
    const inicio = valorExibidoRef.current;
    const destino = Number.isFinite(valor) ? valor : 0;
    const duracaoMs = Math.max(0, duracao) * 1000;

    let frameId = 0;
    let instanteInicial: number | null = null;

    const concluir = (): void => {
      valorExibidoRef.current = destino;
      setValorExibido(destino);
    };

    const movimentoReduzido =
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    if (duracaoMs === 0 || movimentoReduzido || inicio === destino) {
      concluir();
      return;
    }

    const atualizar = (agora: number): void => {
      if (instanteInicial === null) {
        instanteInicial = agora;
      }

      const progresso = Math.min((agora - instanteInicial) / duracaoMs, 1);
      // Curva ease-out cúbica: começa mais rápida e termina suavemente.
      const progressoSuave = 1 - Math.pow(1 - progresso, 3);
      const proximoValor = inicio + (destino - inicio) * progressoSuave;

      valorExibidoRef.current = proximoValor;
      setValorExibido(proximoValor);

      if (progresso < 1) {
        frameId = window.requestAnimationFrame(atualizar);
      } else {
        concluir();
      }
    };

    frameId = window.requestAnimationFrame(atualizar);

    return () => {
      if (frameId) {
        window.cancelAnimationFrame(frameId);
      }
    };
  }, [valor, duracao]);

  const formatador = new Intl.NumberFormat("pt-BR", {
    minimumFractionDigits: casas_decimais,
    maximumFractionDigits: casas_decimais,
  });

  const valorFormatado = formatador.format(valorExibido);
  const valorFinalFormatado = formatador.format(valor);
  const textoAcessivel = [prefixo, valorFinalFormatado, sufixo]
    .filter((parte) => parte.length > 0)
    .join(" ");

  return (
    <section
      style={cardStyle}
      role="group"
      aria-label={`${rotulo}: ${textoAcessivel}`}
    >
      <p style={labelStyle}>{rotulo}</p>

      <div style={valueStyle} aria-hidden="true">
        {prefixo && <span style={affixStyle}>{prefixo}</span>}
        <span>{valorFormatado}</span>
        {sufixo && <span style={affixStyle}>{sufixo}</span>}
      </div>

      <span style={screenReaderOnlyStyle}>{textoAcessivel}</span>
    </section>
  );
};

export default MyComponent;
