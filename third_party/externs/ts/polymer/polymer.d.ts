interface Window {
  readonly customElements: CustomElementRegistry;
}

interface CustomElementRegistry {
  define(name: string, constructor: Function, options?: ElementDefinitionOptions): void;
  get(name: string): any;
  whenDefined(name: string): Promise<void>;
}

interface ElementDefinitionOptions {
  extends: string;
}

declare module Polymer {

  class Element extends HTMLElement {
    $: any;
    $$: any;
    root: HTMLElement;
    shadyRoot: HTMLElement;
    style: CSSStyleDeclaration;
    customStyle: {
      [property: string]: string;
    };
    arrayDelete(path: string, item: string | any): any;
    async(callback: Function, waitTime?: number): any;
    attachedCallback(): void;
    attributeFollows(name: string, toElement: HTMLElement, fromElement: HTMLElement): void;
    cancelAsync(handle: number): void;
    cancelDebouncer(jobName: string): void;
    classFollows(name: string, toElement: HTMLElement, fromElement: HTMLElement): void;
    create(tag: string, props?: Object): HTMLElement;
    debounce(jobName: string, callback: Function, wait?: number): void;
    deserialize(value: string, type: any): any;
    distributeContent(): void;
    domHost(): void;
    elementMatches(selector: string, node: Element): any;
    fire(type: string, detail?: Object, options?: FireOptions): any;
    flushDebouncer(jobName: string): void;
    get(path: string | Array<string | number>): any;
    getContentChildNodes(slctr: string): any;
    getContentChildren(slctr: string): any;
    getNativePrototype(tag: string): any;
    getPropertyInfo(property: string): any;
    importHref(href: string, onload?: Function, onerror?: Function, optAsync?: boolean): any;
    instanceTemplate(template: any): any;
    isDebouncerActive(jobName: string): any;
    linkPaths(to: string, from: string): void;
    listen(node: Element, eventName: string, methodName: string): void;
    mixin(target: Object, source: Object): void;
    notifyPath(path: string, value: any, fromAbove?: any): void;
    notifySplices(path: string, splices: {
      index: number;
      removed: Array<any>;
      addedCount: number;
      object: Array<any>;
      type: "splice";
    }[]): void;
    pop(path: string): any;
    push(path: string, value: any): any;
    reflectPropertyToAttribute(name: string): void;
    resolveUrl(url: string): any;
    scopeSubtree(container: Element, shouldObserve: boolean): void;
    serialize(value: string): any;
    serializeValueToAttribute(value: any, attribute: string, node: Element): void;
    set(path: string | Array<string | number>, value: any, root?: Object): any;
    setScrollDirection(direction: string, node: HTMLElement): void;
    shift(path: string, value: any): any;
    splice(path: string, start: number, deleteCount: number, ...items: any[]): any;
    toggleAttribute(name: string, bool: boolean, node?: HTMLElement): void;
    toggleClass(name: string, bool: boolean, node?: HTMLElement): void;
    transform(transform: string, node?: HTMLElement): void;
    translate3d(x: any, y: any, z: any, node?: HTMLElement): void;
    unlinkPaths(path: string): void;
    unlisten(node: Element, eventName: string, methodName: string): void;
    unshift(path: string, value: any): any;
    updateStyles(): void;
    properties?: Object;
    listeners?: Object;
    behaviors?: Object[];
    observers?: String[];
    factoryImpl?(...args: any[]): void;
    ready?(): void;
    created?(): void;
    attached?(): void;
    detached?(): void;
    attributeChanged?(attrName: string, oldVal: any, newVal: any): void;
    prototype?: Object;
  }

  interface FireOptions {
    node?: HTMLElement | Polymer.Element;
    bubbles?: boolean;
    cancelable?: boolean;
  }

}
