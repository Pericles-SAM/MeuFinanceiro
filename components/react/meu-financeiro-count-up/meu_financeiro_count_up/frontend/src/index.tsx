import {
  FrontendRenderer,
  FrontendRendererArgs,
} from "@streamlit/component-v2-lib";
import { StrictMode } from "react";
import { createRoot, Root } from "react-dom/client";

import MyComponent, {
  MyComponentDataShape,
  MyComponentStateShape,
} from "./MyComponent";

// Mantém uma raiz React por instância do componente Streamlit.
const reactRoots: WeakMap<FrontendRendererArgs["parentElement"], Root> =
  new WeakMap();

const MyComponentRoot: FrontendRenderer<
  MyComponentStateShape,
  MyComponentDataShape
> = (args) => {
  const { data, parentElement } = args;
  const rootElement = parentElement.querySelector(".react-root");

  if (!rootElement) {
    throw new Error("Elemento raiz do React não encontrado.");
  }

  let reactRoot = reactRoots.get(parentElement);

  if (!reactRoot) {
    reactRoot = createRoot(rootElement);
    reactRoots.set(parentElement, reactRoot);
  }

  reactRoot.render(
    <StrictMode>
      <MyComponent {...data} />
    </StrictMode>,
  );

  return () => {
    const root = reactRoots.get(parentElement);

    if (root) {
      root.unmount();
      reactRoots.delete(parentElement);
    }
  };
};

export default MyComponentRoot;
