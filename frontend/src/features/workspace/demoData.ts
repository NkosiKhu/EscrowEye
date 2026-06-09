import type { Profile, WorkerProfile } from "./models";

export const defaultProfile: Profile = {
  firstName: "",
  lastName: "",
  location: "Ikoyi, Lagos",
  serviceArea: "Lagos Island",
  photoUrl: "https://images.unsplash.com/photo-1544723795-3fb6469f5b39?auto=format&fit=crop&w=200&q=80",
  paymentToken: "HBAR",
};

export const serviceCategories = ["Cleaning", "Pool cleaning", "Maintenance", "Airbnb turnover", "Carpentry", "Plumbing", "Electrical repairs", "Handyman"];

export const workers: WorkerProfile[] = [
  {
    id: 1,
    name: "Chijioke Nwosu",
    profession: "Expert window washing",
    rating: "4.8",
    rate: "From ₦80k",
    location: "Ikoyi",
    jobs: 128,
    image: "https://images.unsplash.com/photo-1503387762-592deb58ef4e?auto=format&fit=crop&w=500&q=80",
  },
  {
    id: 2,
    name: "Kurt Kanu",
    profession: "Post-construction cleaning",
    rating: "5.0",
    rate: "From ₦120k",
    location: "Victoria Island",
    jobs: 91,
    image: "https://images.unsplash.com/photo-1580894894513-541e068a3e2b?auto=format&fit=crop&w=500&q=80",
  },
  {
    id: 3,
    name: "Favour Bello",
    profession: "Airbnb turnover specialist",
    rating: "4.9",
    rate: "From ₦65k",
    location: "Surulere",
    jobs: 74,
    image: "https://images.unsplash.com/photo-1565347878134-064b9185ced8?auto=format&fit=crop&w=500&q=80",
  },
];

export const sampleJobs = [
  {
    title: "Window cleaning services for 2 newly built two-storey buildings",
    address: "10b Gerrard Road, Ikoyi, Lagos",
    date: "Sat, 1 Mar 2025",
    amount: "₦200,000",
  },
  {
    title: "Post-construction cleaning for a commercial office space",
    address: "45 Adeola Odeku Street, Victoria Island, Lagos",
    date: "Tue, 4 Mar 2025",
    amount: "₦300,000",
  },
  {
    title: "Deep cleaning services for a newly renovated residential home",
    address: "78 Alhaji Kola Street, Surulere, Lagos",
    date: "Fri, 7 Mar 2025",
    amount: "₦120,000",
  },
];
