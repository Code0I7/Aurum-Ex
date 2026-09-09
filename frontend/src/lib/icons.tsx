import {
  Anchor,
  Antenna,
  Apple,
  Baby,
  Backpack,
  Bandage,
  Banknote,
  Bath,
  Beef,
  Beer,
  Bell,
  Bike,
  Bitcoin,
  Bone,
  BookOpen,
  Bookmark,
  Brain,
  Briefcase,
  Building,
  Building2,
  Bus,
  Cake,
  Calendar,
  Camera,
  Car,
  CarTaxiFront,
  Carrot,
  Cat,
  Church,
  CircleHelp,
  Clapperboard,
  Cloud,
  Code,
  Coffee,
  Coins,
  Cookie,
  CreditCard,
  Croissant,
  CupSoda,
  Dices,
  Dog,
  Droplet,
  Droplets,
  Dumbbell,
  Factory,
  FileText,
  Fish,
  Flame,
  Flower,
  Footprints,
  Fuel,
  Gamepad2,
  Gem,
  Gift,
  Glasses,
  GraduationCap,
  Hammer,
  HandCoins,
  Handshake,
  Headphones,
  Heart,
  HeartPulse,
  Home,
  Hourglass,
  IceCreamCone,
  Key,
  Lamp,
  Landmark,
  Laptop,
  Lock,
  Luggage,
  Mail,
  MessageCircle,
  Milk,
  MoreHorizontal,
  Mountain,
  Music,
  Package,
  PaintRoller,
  Palette,
  ParkingCircle,
  PawPrint,
  Percent,
  Phone,
  PiggyBank,
  Pill,
  Pizza,
  Plane,
  Plug,
  PlusCircle,
  Printer,
  Receipt,
  Repeat,
  Rocket,
  Router,
  Salad,
  Scale,
  School,
  Scissors,
  Shapes,
  Shield,
  Ship,
  Shirt,
  ShoppingBag,
  ShoppingBasket,
  ShoppingCart,
  Smartphone,
  Snowflake,
  Sofa,
  Sparkles,
  Star,
  Stethoscope,
  Sun,
  Syringe,
  Tag,
  Tent,
  Ticket,
  ToyBrick,
  TrainFront,
  Trash2,
  TreePine,
  TrendingDown,
  TrendingUp,
  Truck,
  Tv,
  Umbrella,
  Users,
  Utensils,
  Video,
  Wallet,
  WashingMachine,
  Watch,
  Waves,
  Wifi,
  Wine,
  Wrench,
  Zap,
  ZapOff,
  type LucideIcon,
} from "lucide-react";
import type { TranslationKey } from "@/lib/i18n";

/**
 * Значки категорий.
 *
 * Глифы приходят из пакета `lucide-react` — их там около полутора тысяч.
 * Наружу выведено меньше сотни: список, в котором нужно выбрать один
 * значок, длиннее экрана уже бесполезен, а поиск по полутора тысячам
 * английских имён требует знать, что стакан газировки называется
 * `cup-soda`.
 *
 * Поэтому отобранный набор, разложенный по смыслу, плюс поиск по русским и
 * английским словам: «вода» находит каплю, «жкх» — розетку, «зп» —
 * купюру. Добавить значок — это одна строка в таблице ниже; ключ
 * произвольный, но у уже используемого значка менять его нельзя: в
 * категориях хранится именно эта строка.
 *
 * Раньше карта была плоской — тридцать семь значков подряд без единого
 * заголовка. Найти в ней нужный можно было только перебором глазами, и в
 * половине категорий стоял кошелёк по умолчанию.
 */

export type IconGroupKey =
  | "home"
  | "food"
  | "transport"
  | "health"
  | "family"
  | "money"
  | "work"
  | "leisure"
  | "things"
  | "tech"
  | "other";

/** Заголовки разделов в выбирателе. Порядок задаёт порядок разделов:
 *  сверху то, что заводят чаще. */
export const ICON_GROUPS: { key: IconGroupKey; labelKey: TranslationKey }[] = [
  { key: "home", labelKey: "icons.group.home" },
  { key: "food", labelKey: "icons.group.food" },
  { key: "transport", labelKey: "icons.group.transport" },
  { key: "health", labelKey: "icons.group.health" },
  { key: "family", labelKey: "icons.group.family" },
  { key: "money", labelKey: "icons.group.money" },
  { key: "work", labelKey: "icons.group.work" },
  { key: "leisure", labelKey: "icons.group.leisure" },
  { key: "things", labelKey: "icons.group.things" },
  { key: "tech", labelKey: "icons.group.tech" },
  { key: "other", labelKey: "icons.group.other" },
];

interface IconSpec {
  component: LucideIcon;
  group: IconGroupKey;
  /** Слова для поиска — по-русски и по-английски: интерфейс двуязычный, и
   *  искать человек будет на своём языке. */
  keywords: string;
}

// Ключи прежних значков сохранены как были: в категориях лежит именно
// строка, и переименование ключа стёрло бы значок у живой категории.
const ICONS: Record<string, IconSpec> = {
  // --- Дом и быт ---
  home: { component: Home, group: "home", keywords: "дом квартира жильё жилье ипотека аренда home house rent" },
  "building-2": { component: Building2, group: "home", keywords: "дом здание жкх квартира building apartment" },
  sofa: { component: Sofa, group: "home", keywords: "мебель диван интерьер furniture sofa couch" },
  lamp: { component: Lamp, group: "home", keywords: "свет лампа электричество light lamp" },
  plug: { component: Plug, group: "home", keywords: "жкх электричество розетка счета utilities plug power" },
  flame: { component: Flame, group: "home", keywords: "газ отопление тепло gas heating" },
  droplet: { component: Droplet, group: "home", keywords: "вода жкх счётчик счетчик water" },
  bath: { component: Bath, group: "home", keywords: "ванная сантехника душ bath shower" },
  "washing-machine": { component: WashingMachine, group: "home", keywords: "стирка техника прачечная laundry washing" },
  wrench: { component: Wrench, group: "home", keywords: "ремонт сервис починка repair wrench tools" },
  hammer: { component: Hammer, group: "home", keywords: "ремонт стройка hammer repair build" },
  "paint-roller": { component: PaintRoller, group: "home", keywords: "ремонт краска отделка paint renovation" },
  "trash-2": { component: Trash2, group: "home", keywords: "мусор вывоз жкх trash garbage" },

  // --- Еда ---
  "shopping-basket": { component: ShoppingBasket, group: "food", keywords: "продукты магазин корзина groceries basket" },
  "shopping-cart": { component: ShoppingCart, group: "food", keywords: "продукты тележка супермаркет cart supermarket" },
  utensils: { component: Utensils, group: "food", keywords: "кафе ресторан еда обед restaurant dining" },
  coffee: { component: Coffee, group: "food", keywords: "кофе кофейня чай coffee tea" },
  "cup-soda": { component: CupSoda, group: "food", keywords: "напитки вода газировка drinks soda" },
  beer: { component: Beer, group: "food", keywords: "пиво алкоголь бар beer alcohol bar" },
  wine: { component: Wine, group: "food", keywords: "вино алкоголь wine alcohol" },
  pizza: { component: Pizza, group: "food", keywords: "пицца фастфуд доставка pizza fastfood delivery" },
  apple: { component: Apple, group: "food", keywords: "фрукты яблоко fruit apple" },
  carrot: { component: Carrot, group: "food", keywords: "овощи морковь vegetables carrot" },
  salad: { component: Salad, group: "food", keywords: "салат зож овощи salad healthy" },
  croissant: { component: Croissant, group: "food", keywords: "выпечка хлеб булочная bakery bread" },
  milk: { component: Milk, group: "food", keywords: "молоко молочное dairy milk" },
  cake: { component: Cake, group: "food", keywords: "торт десерт праздник cake dessert" },
  cookie: { component: Cookie, group: "food", keywords: "сладкое печенье sweets cookie" },
  "ice-cream-cone": { component: IceCreamCone, group: "food", keywords: "мороженое сладкое ice cream" },
  fish: { component: Fish, group: "food", keywords: "рыба морепродукты fish seafood" },
  beef: { component: Beef, group: "food", keywords: "мясо стейк meat beef" },

  // --- Транспорт ---
  car: { component: Car, group: "transport", keywords: "машина авто транспорт car auto" },
  fuel: { component: Fuel, group: "transport", keywords: "бензин заправка топливо fuel gas petrol" },
  "parking-circle": { component: ParkingCircle, group: "transport", keywords: "парковка стоянка parking" },
  bus: { component: Bus, group: "transport", keywords: "автобус проезд транспорт bus transit" },
  "train-front": { component: TrainFront, group: "transport", keywords: "поезд метро электричка train metro" },
  "car-taxi-front": { component: CarTaxiFront, group: "transport", keywords: "такси taxi cab" },
  bike: { component: Bike, group: "transport", keywords: "велосипед самокат bike bicycle" },
  plane: { component: Plane, group: "transport", keywords: "самолёт самолет перелёт отпуск flight plane" },
  ship: { component: Ship, group: "transport", keywords: "паром круиз корабль ship ferry" },
  truck: { component: Truck, group: "transport", keywords: "доставка грузовик перевозка delivery truck" },
  footprints: { component: Footprints, group: "transport", keywords: "пешком прогулка шаги walk steps" },

  // --- Здоровье ---
  "heart-pulse": { component: HeartPulse, group: "health", keywords: "здоровье врач медицина health medical" },
  pill: { component: Pill, group: "health", keywords: "аптека лекарства таблетки pharmacy medicine" },
  stethoscope: { component: Stethoscope, group: "health", keywords: "врач клиника приём прием doctor clinic" },
  syringe: { component: Syringe, group: "health", keywords: "прививка укол анализы vaccine injection" },
  bandage: { component: Bandage, group: "health", keywords: "травма пластырь помощь injury bandage" },
  dumbbell: { component: Dumbbell, group: "health", keywords: "спорт зал фитнес gym fitness sport" },
  brain: { component: Brain, group: "health", keywords: "психолог терапия ментальное therapy mental" },
  glasses: { component: Glasses, group: "health", keywords: "очки зрение оптика glasses optics" },
  scissors: { component: Scissors, group: "health", keywords: "парикмахер стрижка салон barber haircut" },

  // --- Семья ---
  baby: { component: Baby, group: "family", keywords: "ребёнок ребенок дети малыш baby child" },
  "toy-brick": { component: ToyBrick, group: "family", keywords: "игрушки дети toys kids" },
  dog: { component: Dog, group: "family", keywords: "собака питомец животные dog pet" },
  cat: { component: Cat, group: "family", keywords: "кошка кот питомец cat pet" },
  "paw-print": { component: PawPrint, group: "family", keywords: "питомцы ветеринар животные pets vet" },
  bone: { component: Bone, group: "family", keywords: "корм питомец зоомагазин petfood" },
  "graduation-cap": { component: GraduationCap, group: "family", keywords: "образование учёба учеба вуз education study" },
  school: { component: School, group: "family", keywords: "школа садик education school" },
  "book-open": { component: BookOpen, group: "family", keywords: "книги чтение курсы books reading" },
  backpack: { component: Backpack, group: "family", keywords: "школа рюкзак сборы school backpack" },
  users: { component: Users, group: "family", keywords: "семья люди друзья family people" },

  // --- Деньги ---
  banknote: { component: Banknote, group: "money", keywords: "зарплата зп деньги доход salary money income" },
  wallet: { component: Wallet, group: "money", keywords: "кошелёк кошелек счёт счет наличные wallet cash" },
  coins: { component: Coins, group: "money", keywords: "мелочь монеты сбережения coins savings" },
  "hand-coins": { component: HandCoins, group: "money", keywords: "подработка чаевые перевод tips freelance" },
  "piggy-bank": { component: PiggyBank, group: "money", keywords: "накопления копилка цель savings goal" },
  "credit-card": { component: CreditCard, group: "money", keywords: "карта кредит банк card credit bank" },
  landmark: { component: Landmark, group: "money", keywords: "банк налоги государство bank tax government" },
  "trending-up": { component: TrendingUp, group: "money", keywords: "инвестиции рост доход investments growth" },
  "trending-down": { component: TrendingDown, group: "money", keywords: "убыток падение потери loss decline" },
  bitcoin: { component: Bitcoin, group: "money", keywords: "крипта биткоин crypto bitcoin" },
  gem: { component: Gem, group: "money", keywords: "золото металлы драгоценности gold metals jewelry" },
  receipt: { component: Receipt, group: "money", keywords: "чек счёт счет квитанция receipt bill" },
  percent: { component: Percent, group: "money", keywords: "проценты кредит ставка percent interest" },
  scale: { component: Scale, group: "money", keywords: "долг баланс суд debt balance legal" },

  // --- Работа ---
  briefcase: { component: Briefcase, group: "work", keywords: "работа офис бизнес work office business" },
  code: { component: Code, group: "work", keywords: "разработка фриланс ит code dev freelance" },
  laptop: { component: Laptop, group: "work", keywords: "техника ноутбук компьютер laptop computer" },
  printer: { component: Printer, group: "work", keywords: "печать канцелярия офис printer office" },
  building: { component: Building, group: "work", keywords: "офис аренда компания office company" },
  factory: { component: Factory, group: "work", keywords: "производство завод вахта factory industry" },
  "file-text": { component: FileText, group: "work", keywords: "документы бумаги договор documents papers" },
  handshake: { component: Handshake, group: "work", keywords: "сделка клиент договор deal client" },

  // --- Досуг ---
  clapperboard: { component: Clapperboard, group: "leisure", keywords: "кино фильмы развлечения movies cinema" },
  "gamepad-2": { component: Gamepad2, group: "leisure", keywords: "игры приставка games gaming" },
  music: { component: Music, group: "leisure", keywords: "музыка концерт music concert" },
  headphones: { component: Headphones, group: "leisure", keywords: "подписка музыка наушники headphones audio" },
  video: { component: Video, group: "leisure", keywords: "видео стриминг подписка video streaming" },
  // В lucide нет глифов торговых марок — видеокамера ближайшее, что есть.
  youtube: { component: Video, group: "leisure", keywords: "ютуб видео подписка youtube video" },
  ticket: { component: Ticket, group: "leisure", keywords: "билеты театр концерт tickets event" },
  palette: { component: Palette, group: "leisure", keywords: "хобби творчество искусство hobby art" },
  camera: { component: Camera, group: "leisure", keywords: "фото камера съёмка photo camera" },
  tv: { component: Tv, group: "leisure", keywords: "телевизор подписка тв tv streaming" },
  dices: { component: Dices, group: "leisure", keywords: "настолки азарт игры boardgames" },
  tent: { component: Tent, group: "leisure", keywords: "поход туризм палатка camping hiking" },
  mountain: { component: Mountain, group: "leisure", keywords: "горы природа путешествия mountains travel" },
  "tree-pine": { component: TreePine, group: "leisure", keywords: "природа дача лес nature forest" },
  luggage: { component: Luggage, group: "leisure", keywords: "отпуск чемодан путешествие vacation travel" },

  // --- Вещи ---
  "shopping-bag": { component: ShoppingBag, group: "things", keywords: "покупки шопинг магазин shopping" },
  shirt: { component: Shirt, group: "things", keywords: "одежда вещи гардероб clothes apparel" },
  watch: { component: Watch, group: "things", keywords: "часы аксессуары watch accessories" },
  gift: { component: Gift, group: "things", keywords: "подарок праздник gift present" },
  flower: { component: Flower, group: "things", keywords: "цветы букет подарок flowers" },
  sparkles: { component: Sparkles, group: "things", keywords: "красота уход косметика beauty cosmetics" },
  package: { component: Package, group: "things", keywords: "посылка доставка заказ parcel package" },
  droplets: { component: Droplets, group: "things", keywords: "химия чистящее уборка cleaning household" },

  // --- Связь и техника ---
  smartphone: { component: Smartphone, group: "tech", keywords: "телефон связь мобильный phone mobile" },
  phone: { component: Phone, group: "tech", keywords: "связь звонки телефон calls phone" },
  wifi: { component: Wifi, group: "tech", keywords: "интернет вайфай связь internet wifi" },
  router: { component: Router, group: "tech", keywords: "интернет роутер провайдер router isp" },
  antenna: { component: Antenna, group: "tech", keywords: "тв антенна связь antenna tv" },
  cloud: { component: Cloud, group: "tech", keywords: "облако подписка хранилище cloud storage" },
  mail: { component: Mail, group: "tech", keywords: "почта письма mail post" },
  "message-circle": { component: MessageCircle, group: "tech", keywords: "сообщения связь чат messages chat" },

  // --- Прочее ---
  repeat: { component: Repeat, group: "other", keywords: "подписка регулярное повтор subscription recurring" },
  calendar: { component: Calendar, group: "other", keywords: "график план дата calendar schedule" },
  hourglass: { component: Hourglass, group: "other", keywords: "время ожидание time waiting" },
  shield: { component: Shield, group: "other", keywords: "страховка защита insurance protection" },
  umbrella: { component: Umbrella, group: "other", keywords: "страховка запас резерв insurance rainy" },
  lock: { component: Lock, group: "other", keywords: "безопасность подписка пароль security password" },
  key: { component: Key, group: "other", keywords: "аренда ключи жильё keys rent" },
  bell: { component: Bell, group: "other", keywords: "напоминание уведомление reminder alert" },
  heart: { component: Heart, group: "other", keywords: "благотворительность донат помощь charity donation" },
  church: { component: Church, group: "other", keywords: "пожертвование храм donation church" },
  star: { component: Star, group: "other", keywords: "избранное важное favorite star" },
  bookmark: { component: Bookmark, group: "other", keywords: "закладка метка bookmark" },
  anchor: { component: Anchor, group: "other", keywords: "постоянное якорь anchor fixed" },
  rocket: { component: Rocket, group: "other", keywords: "старт запуск проект startup launch" },
  sun: { component: Sun, group: "other", keywords: "лето отпуск сезон summer season" },
  snowflake: { component: Snowflake, group: "other", keywords: "зима сезон отопление winter season" },
  waves: { component: Waves, group: "other", keywords: "море отпуск бассейн sea pool" },
  tag: { component: Tag, group: "other", keywords: "метка ярлык цена tag label" },
  shapes: { component: Shapes, group: "other", keywords: "прочее разное misc other" },
  "plus-circle": { component: PlusCircle, group: "other", keywords: "прочее добавить plus other" },
  "more-horizontal": { component: MoreHorizontal, group: "other", keywords: "прочее разное other misc" },
  "circle-help": { component: CircleHelp, group: "other", keywords: "неизвестно вопрос unknown question" },
  zap: { component: Zap, group: "other", keywords: "быстро энергия срочное fast energy" },
  "zap-off": { component: ZapOff, group: "other", keywords: "отключено не учитывать excluded off" },
};

export function getCategoryIcon(icon: string | null | undefined): LucideIcon {
  // Незнакомый ключ рисуется кошельком, а не роняет экран: значок
  // категории — украшение, и падать из-за него нечему.
  if (!icon) return Wallet;
  return ICONS[icon]?.component ?? Wallet;
}

export interface IconOption {
  key: string;
  component: LucideIcon;
  group: IconGroupKey;
  keywords: string;
}

/** Весь набор для выбирателя, разложенный по разделам в их порядке. */
export const CATEGORY_ICON_OPTIONS: IconOption[] = ICON_GROUPS.flatMap((group) =>
  Object.entries(ICONS)
    .filter(([, spec]) => spec.group === group.key)
    .map(([key, spec]) => ({ key, ...spec }))
);
