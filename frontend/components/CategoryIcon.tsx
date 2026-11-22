"use client";
// Category icons: a Fluent icon on a tinted circle in the category colour.
// Categories without a chosen icon get one guessed from their name, so the
// built-in categories look right without any setup.
import {
  AirplaneRegular, AnimalDogRegular, ArrowTrendingLinesRegular, BeachRegular,
  BedRegular, BookRegular, BoxRegular, BriefcaseRegular, BuildingBankRegular,
  BuildingRegular, CartRegular, CircleSmallRegular, DocumentRegular,
  DrinkCoffeeRegular, DumbbellRegular, FlashRegular, FoodRegular,
  GamesRegular, GasPumpRegular, GavelRegular, GiftRegular, GlassesRegular,
  HandOpenHeartRegular, HatGraduationRegular, HeartPulseRegular, HomeRegular,
  LaptopRegular, LightbulbRegular, MoneyRegular, MoviesAndTvRegular,
  MusicNote2Regular, PeopleTeamRegular, PersonMoneyRegular, PhoneRegular,
  PillRegular, ReceiptRegular, SavingsRegular, ShieldRegular, ShirtRegular,
  ShoppingBagRegular, SparkleRegular, SportRegular, StethoscopeRegular,
  TagRegular, TicketDiagonalRegular, ToolboxRegular, UmbrellaRegular,
  VehicleBusRegular, VehicleCabRegular, VehicleCarRegular, WalletRegular,
  WaterRegular, Wifi1Regular, WrenchRegular,
} from "@fluentui/react-icons";
import type { FluentIcon } from "@fluentui/react-icons";

export const ICONS: Record<string, FluentIcon> = {
  cart: CartRegular, food: FoodRegular, coffee: DrinkCoffeeRegular,
  home: HomeRegular, bolt: FlashRegular, wifi: Wifi1Regular,
  phone: PhoneRegular, shield: ShieldRegular, car: VehicleCarRegular,
  bus: VehicleBusRegular, fuel: GasPumpRegular, taxi: VehicleCabRegular,
  health: HeartPulseRegular, doctor: StethoscopeRegular, pill: PillRegular,
  shirt: ShirtRegular, laptop: LaptopRegular, bag: ShoppingBagRegular,
  games: GamesRegular, movie: MoviesAndTvRegular, music: MusicNote2Regular,
  ticket: TicketDiagonalRegular, sport: SportRegular, gym: DumbbellRegular,
  travel: AirplaneRegular, beach: BeachRegular, book: BookRegular,
  school: HatGraduationRegular, bank: BuildingBankRegular,
  receipt: ReceiptRegular, tax: GavelRegular, gift: GiftRegular,
  charity: HandOpenHeartRegular, money: MoneyRegular, work: BriefcaseRegular,
  salary: PersonMoneyRegular, savings: SavingsRegular, wallet: WalletRegular,
  invest: ArrowTrendingLinesRegular, tag: TagRegular, box: BoxRegular,
  pet: AnimalDogRegular, tools: WrenchRegular, toolbox: ToolboxRegular,
  water: WaterRegular, light: LightbulbRegular, building: BuildingRegular,
  bed: BedRegular, glasses: GlassesRegular, umbrella: UmbrellaRegular,
  document: DocumentRegular, family: PeopleTeamRegular, star: SparkleRegular,
  other: CircleSmallRegular,
};

// Keyword → icon, checked in order against the lower-case category name
// (English, French and Arabic words for the built-in categories).
const GUESS: [RegExp, string][] = [
  [/grocer|épicer|courses|supermarch|بقال/, "cart"],
  [/restaurant|dining|food|aliment|nourrit|طعام|مطعم/, "food"],
  [/coffee|café|snack|قهوة/, "coffee"],
  [/rent|loyer|housing|logement|mortgage|hypoth|سكن|إيجار/, "home"],
  [/utilit|électric|electric|energy|énergie|كهرباء/, "bolt"],
  [/internet|wifi/, "wifi"], [/phone|téléphone|mobile|هاتف/, "phone"],
  [/insurance|assurance|تأمين/, "shield"],
  [/fuel|carbur|essence|gas|وقود/, "fuel"], [/taxi|ride|uber/, "taxi"],
  [/public transport|transport public|bus|train|tram|نقل/, "bus"],
  [/car|voiture|auto|transport|سيارة/, "car"],
  [/doctor|dentist|médecin|dentiste|طبيب/, "doctor"],
  [/pharma|صيدل/, "pill"], [/health|santé|صحة/, "health"],
  [/cloth|vêtement|ملابس/, "shirt"], [/electronic|électroni/, "laptop"],
  [/shopping|achats|تسوق/, "bag"], [/home & garden|maison|jardin/, "home"],
  [/subscri|abonnement|اشتراك/, "music"],
  [/entertain|divertis|loisir|leisure|ترفيه/, "movie"],
  [/sport|gym|fitness|رياضة/, "sport"], [/travel|voyage|holiday|سفر/, "travel"],
  [/course|cours|education|éducation|school|تعليم/, "school"],
  [/book|livre|كتب/, "book"], [/bank|banque|fee|frais|بنك/, "bank"],
  [/tax|impôt|ضريبة/, "tax"], [/gift|cadeau|هدية/, "gift"],
  [/donation|don\b|charity|تبرع/, "charity"], [/family|famille|عائلة/, "family"],
  [/salary|salaire|راتب/, "salary"], [/bonus|prime|مكافأة/, "money"],
  [/freelance|indépendant/, "work"], [/dividend|interest|intérêt|invest/, "invest"],
  [/refund|rembours|استرداد/, "receipt"], [/saving|épargne|ادخار/, "savings"],
  [/pet|animal|حيوان/, "pet"], [/finance|مالية/, "wallet"],
  [/other|autre|أخرى/, "other"],
];

export function guessIcon(name: string): string {
  const n = name.toLowerCase();
  return GUESS.find(([re]) => re.test(n))?.[1] ?? "tag";
}

/** A deterministic soft colour for categories without their own colour. */
const PALETTE = ["#0072B2", "#E69F00", "#009E73", "#D55E00", "#56B4E9",
  "#CC79A7", "#6750A4", "#00796B", "#AD1457", "#827717"];
export function categoryColor(name: string, color?: string | null) {
  if (color) return color;
  let h = 0;
  for (const ch of name) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return PALETTE[h % PALETTE.length];
}

/** Which of the five Expressive shapes a category sits on, stable per name. */
function shapeIndex(name: string) {
  let h = 7;
  for (const ch of name) h = (h * 33 + ch.charCodeAt(0)) >>> 0;
  return h % 5;
}

export function CategoryIcon({ name, icon, color, size = 32 }: {
  name: string; icon?: string | null; color?: string | null; size?: number;
}) {
  const Icon = ICONS[icon || guessIcon(name)] ?? TagRegular;
  const c = categoryColor(name, color);
  return (
    <span className={`cat-icon s-${shapeIndex(name)}`} aria-hidden style={{
      width: size, height: size, color: c, ["--cat" as string]: c,
    }}>
      <Icon fontSize={Math.round(size * 0.56)} />
    </span>
  );
}

/** A grid of icons to choose from. */
export function IconPicker({ value, color, onChange }: {
  value: string | null; color?: string | null; onChange: (icon: string) => void;
}) {
  const c = color || "var(--accent)";
  return (
    <div className="icon-grid" role="listbox">
      {Object.entries(ICONS).map(([id, Icon]) => (
        <button key={id} type="button" role="option" aria-selected={value === id}
          aria-label={id} title={id}
          className={value === id ? "icon-opt selected" : "icon-opt"}
          style={value === id ? { color: c, borderColor: c } : undefined}
          onClick={() => onChange(id)}>
          <Icon fontSize={20} />
        </button>))}
    </div>
  );
}
