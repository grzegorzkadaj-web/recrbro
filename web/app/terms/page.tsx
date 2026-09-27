import type { Metadata } from "next";
import { LegalFooter } from "../legal-footer";

export const metadata: Metadata = {
  title: "Terms of Service | RecrBro",
};

export default function TermsPage() {
  return (
    <main className="legalPage">
      <a className="brand" href="/" aria-label="RecrBro">
        <span className="logo" aria-hidden="true">R<i /></span>
        <span>RecrBro</span>
      </a>
      <article>
        <p className="sectionNumber">Obowiązuje od 27 września 2026 r.</p>
        <h1>Regulamin serwisu RecrBro</h1>

        <h2>1. Usługodawca</h2>
        <p>
          Właścicielem i usługodawcą serwisu RecrBro jest AKID SI Grzegorz
          Kadaj, NIP: 1181363065, adres: ul. Okulickiego 14, 05-110 Jabłonna,
          dalej „Usługodawca”.
        </p>

        <h2>2. Zakres usługi</h2>
        <p>
          RecrBro umożliwia utworzenie konta, zapisanie profilu zawodowego,
          analizę przesłanego CV, wyszukiwanie ofert pracy, ich automatyczną
          ocenę względem profilu oraz oznaczanie ofert jako wykorzystane.
          Wyniki i oceny mają charakter informacyjny i pomocniczy.
        </p>

        <h2>3. Konto i wymagania techniczne</h2>
        <p>
          Rejestracja wymaga podania prawdziwego adresu e-mail, ustanowienia
          hasła, przejścia zabezpieczenia antybotowego oraz akceptacji
          Regulaminu i zapoznania się z Polityką prywatności. Użytkownik
          odpowiada za poufność danych dostępowych i działania wykonane przy
          użyciu jego konta. Do korzystania z serwisu potrzebne są aktualna
          przeglądarka, dostęp do Internetu i włączona obsługa JavaScript.
        </p>

        <h2>4. Źródła ofert i odpowiedzialność</h2>
        <p>
          <strong>
            Źródła ofert pracy są pozyskiwane za pośrednictwem usługi Tavily.
            Usługodawca nie odpowiada za ich jakość, kompletność, dokładność,
            aktualność ani dostępność.
          </strong>
        </p>
        <p>
          Oferty, opisy i odnośniki pochodzą od niezależnych podmiotów
          zewnętrznych. RecrBro podejmuje automatyczne próby odrzucenia ofert
          nieaktywnych i niedopasowanych, lecz nie gwarantuje poprawności
          wyników, dostępności stanowiska, odpowiedzi pracodawcy ani
          zatrudnienia. Przed aplikowaniem użytkownik powinien samodzielnie
          zweryfikować ofertę, pracodawcę, warunki i bezpieczeństwo odnośnika.
        </p>

        <h2>5. Automatyczna analiza</h2>
        <p>
          Analiza CV, dopasowanie i treści generowane automatycznie mogą
          zawierać błędy. Nie stanowią doradztwa prawnego, finansowego ani
          gwarancji wyniku rekrutacji. Użytkownik powinien sprawdzić informacje
          przed podjęciem decyzji zawodowej.
        </p>

        <h2>6. Zasady korzystania</h2>
        <p>
          Zabronione jest dostarczanie treści bezprawnych, naruszanie praw osób
          trzecich, obchodzenie zabezpieczeń, zakłócanie działania serwisu oraz
          używanie go w sposób sprzeczny z prawem. Użytkownik może przesyłać
          wyłącznie dane i dokumenty, do których wykorzystania jest uprawniony.
        </p>

        <h2>7. Plany, kredyty i płatności</h2>
        <p>
          Zakres planów, limity i ceny są prezentowane w serwisie przed
          zakupem. Płatności obsługuje zewnętrzny operator Przelewy24.
          Przyznanie płatnych kredytów następuje po potwierdzeniu płatności.
          Dostępne kredyty są pomniejszane zgodnie z rzeczywistym użyciem usług
          AI i zasadami widocznymi w serwisie.
        </p>

        <h2>8. Dostępność i zmiany</h2>
        <p>
          Usługodawca może prowadzić prace techniczne, zmieniać funkcje lub
          czasowo ograniczyć dostęp, szczególnie z przyczyn bezpieczeństwa,
          awarii albo zmian po stronie dostawców zewnętrznych. Istotne zmiany
          Regulaminu będą komunikowane w serwisie; dalsze korzystanie może
          wymagać ponownej akceptacji.
        </p>

        <h2>9. Rezygnacja i reklamacje</h2>
        <p>
          Użytkownik może zrezygnować z korzystania z serwisu i zażądać
          usunięcia konta. Reklamacje można składać pisemnie na adres
          Usługodawcy wskazany w punkcie 1, opisując problem i oczekiwany sposób
          rozwiązania. Reklamacja zostanie rozpatrzona bez zbędnej zwłoki, nie
          później niż w terminie 14 dni.
        </p>

        <h2>10. Prawo właściwe</h2>
        <p>
          Do Regulaminu stosuje się prawo polskie. Postanowienia Regulaminu nie
          ograniczają bezwzględnie obowiązujących praw konsumenta.
        </p>
      </article>
      <LegalFooter />
    </main>
  );
}
