import type { Metadata } from "next";
import { LegalFooter } from "../legal-footer";

export const metadata: Metadata = {
  title: "Privacy Policy | RecrBro",
};

export default function PrivacyPage() {
  return (
    <main className="legalPage">
      <a className="brand" href="/" aria-label="RecrBro">
        <span className="logo" aria-hidden="true">R<i /></span>
        <span>RecrBro</span>
      </a>
      <article>
        <p className="sectionNumber">Obowiązuje od 27 września 2026 r.</p>
        <h1>Polityka prywatności</h1>

        <h2>1. Administrator danych</h2>
        <p>
          Administratorem danych osobowych jest AKID SI Grzegorz Kadaj, NIP:
          1181363065, adres: ul. Okulickiego 14, 05-110 Jabłonna. W sprawach
          dotyczących danych osobowych można kontaktować się pisemnie na ten
          adres.
        </p>

        <h2>2. Zakres przetwarzanych danych</h2>
        <p>
          Serwis może przetwarzać imię, adres e-mail, skrót hasła, dane
          profilu zawodowego, treść i nazwę pliku CV, preferencje wyszukiwania,
          historię wyszukiwań i aplikowania, dane o wykorzystaniu kredytów,
          płatnościach, sesji, adresie IP oraz dane techniczne przeglądarki.
          Operator płatności przekazuje wyłącznie informacje potrzebne do
          identyfikacji i potwierdzenia transakcji.
        </p>

        <h2>3. Cele i podstawy prawne</h2>
        <p>
          Dane są przetwarzane w celu utworzenia i obsługi konta, wykonania
          żądanych wyszukiwań i analiz, obsługi płatności, zabezpieczenia
          serwisu, rozpatrywania reklamacji oraz realizacji obowiązków
          rachunkowych i prawnych. Podstawą jest wykonanie umowy, obowiązek
          prawny oraz prawnie uzasadniony interes administratora polegający na
          zapewnieniu bezpieczeństwa i dochodzeniu roszczeń.
        </p>

        <h2>4. Odbiorcy i usługi zewnętrzne</h2>
        <p>
          Dane mogą być powierzane dostawcom hostingu i infrastruktury oraz
          usługom niezbędnym do działania RecrBro. Zapytania wyszukiwania i
          informacje potrzebne do odnalezienia ofert są przekazywane do Tavily.
          Dane potrzebne do analizy CV, ofert i obsługi asystenta mogą być
          przekazywane do OpenAI. Cloudflare przetwarza dane techniczne podczas
          weryfikacji Turnstile, a Przelewy24 przetwarza dane płatności.
          Dostawcy mogą przetwarzać dane poza Europejskim Obszarem Gospodarczym
          na podstawie właściwych mechanizmów legalizujących transfer.
        </p>

        <h2>5. Okres przechowywania</h2>
        <p>
          Dane konta są przechowywane przez okres korzystania z serwisu, a po
          jego zakończeniu przez czas potrzebny do rozliczeń, obsługi roszczeń
          i wykonania obowiązków prawnych. Dane techniczne i bezpieczeństwa są
          przechowywane tylko tak długo, jak jest to potrzebne do ochrony
          serwisu. Dokument CV i dane profilu mogą zostać usunięte na żądanie
          wraz z kontem, z zastrzeżeniem obowiązków ustawowych.
        </p>

        <h2>6. Prawa użytkownika</h2>
        <p>
          Użytkownik ma prawo dostępu do danych, ich sprostowania, usunięcia,
          ograniczenia przetwarzania, przenoszenia i wniesienia sprzeciwu, gdy
          podstawą jest uzasadniony interes. Ma również prawo wnieść skargę do
          Prezesa Urzędu Ochrony Danych Osobowych.
        </p>

        <h2>7. Bezpieczeństwo i przechowywanie w przeglądarce</h2>
        <p>
          Hasła są przechowywane w postaci skrótu kryptograficznego. Token
          sesji jest zapisywany w pamięci lokalnej przeglądarki, aby utrzymać
          zalogowanie. Turnstile i pozostali dostawcy zewnętrzni mogą korzystać
          z własnych technologii niezbędnych do bezpieczeństwa i realizacji
          usług. Wylogowanie usuwa lokalny token sesji z urządzenia.
        </p>

        <h2>8. Zmiany polityki</h2>
        <p>
          Polityka może być aktualizowana wraz ze zmianą prawa, funkcji lub
          dostawców. Aktualna wersja i data obowiązywania są publikowane na tej
          stronie.
        </p>
      </article>
      <LegalFooter />
    </main>
  );
}
