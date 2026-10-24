import appMark from "../assets/app-mark.svg";

/** The same static book/discovery mark used by the wordmarks and the favicon. */
export function AppMark() {
  return <img className="app-mark" src={appMark} width={48} height={48} alt="" aria-hidden="true" />;
}
