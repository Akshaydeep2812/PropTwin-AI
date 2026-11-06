import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate, useParams } from "react-router-dom";
import { z } from "zod";
import { PageGuide } from "../components/guide";
import { CONDITIONS, PROPERTY_TYPES } from "../components/property";
import { Button, Card, ErrorNote, Loadable, PageHeader, SelectField, TextAreaField, TextField } from "../components/ui";
import { useAsync } from "../hooks/useAsync";
import { api } from "../services/api";

const blankToUndefined = (value) => (value === "" || value === null || value === undefined ? undefined : value);
const optionalNumber = (schema) => z.preprocess(blankToUndefined, schema.optional());
const number = z.coerce.number({ invalid_type_error: "Enter a number." });
const THIS_YEAR = new Date().getFullYear();

export const propertySchema = z
  .object({
    title: z.string().trim().min(3, "Use at least 3 characters.").max(180),
    description: z.string().max(5000).optional(),
    property_type: z.enum(["apartment", "house", "villa", "townhouse", "plot", "commercial"]),
    address_line1: z.string().trim().min(1, "Enter the street address.").max(200),
    locality: z.string().max(100).optional(),
    city: z.string().trim().min(1, "Enter the city.").max(100),
    state: z.string().trim().min(1, "Enter the state.").max(100),
    postal_code: z.string().trim().regex(/^[A-Za-z0-9 -]{3,20}$/, "Enter a valid postal code."),
    built_up_area_sqft: optionalNumber(number.positive("Must be greater than zero.")),
    land_area_sqft: optionalNumber(number.positive("Must be greater than zero.")),
    bedrooms: optionalNumber(number.int("Use a whole number.").min(0, "Cannot be negative.")),
    bathrooms: optionalNumber(number.int("Use a whole number.").min(0, "Cannot be negative.")),
    construction_year: optionalNumber(number.int("Use a whole number.").min(1800, "Enter a year from 1800.").max(THIS_YEAR + 5, "This year is too far ahead.")),
    floor_number: optionalNumber(number.int("Use a whole number.")),
    total_floors: optionalNumber(number.int("Use a whole number.").min(1, "Must be at least 1.")),
    condition: z.preprocess(blankToUndefined, z.enum(["poor", "fair", "good", "very_good", "excellent"]).optional()),
    amenities: z.string().optional(),
    parking_spaces: optionalNumber(number.int("Use a whole number.").min(0, "Cannot be negative.")),
    asking_price: optionalNumber(number.positive("Must be greater than zero.")),
    monthly_rent: optionalNumber(number.min(0, "Cannot be negative.")),
    last_sale_price: optionalNumber(number.positive("Must be greater than zero.")),
    last_sale_date: z.preprocess(blankToUndefined, z.string().optional()),
    listing_status: z.enum(["draft", "listed", "under_offer", "sold", "archived"]),
  })
  .refine((values) => values.floor_number === undefined || values.total_floors === undefined || values.floor_number <= values.total_floors, {
    path: ["floor_number"],
    message: "Floor number cannot be greater than total floors.",
  });

const NULLABLE = ["built_up_area_sqft", "land_area_sqft", "bedrooms", "bathrooms", "construction_year", "floor_number", "total_floors", "condition", "asking_price", "monthly_rent", "last_sale_price", "last_sale_date"];
const MONEY_OR_AREA = ["built_up_area_sqft", "land_area_sqft", "asking_price", "monthly_rent", "last_sale_price"];

function toPayload(values, isEdit) {
  const payload = {
    ...values,
    description: values.description || null,
    locality: values.locality || null,
    amenities: (values.amenities ?? "").split(",").map((item) => item.trim()).filter(Boolean),
    parking_spaces: values.parking_spaces ?? 0,
  };
  for (const field of NULLABLE) {
    if (payload[field] === undefined) payload[field] = null;
  }
  // Numbers from the form are sent as exact decimal strings, not floats.
  for (const field of MONEY_OR_AREA) {
    if (payload[field] !== null) payload[field] = Number(payload[field]).toFixed(2);
  }
  if (!isEdit && !["draft", "listed"].includes(payload.listing_status)) payload.listing_status = "draft";
  return payload;
}

function toFormValues(property) {
  const values = { ...property, amenities: property.amenities.join(", ") };
  for (const key of Object.keys(values)) {
    if (values[key] === null) values[key] = "";
  }
  return values;
}

function PropertyForm({ initial, propertyId }) {
  const navigate = useNavigate();
  const [error, setError] = useState(null);
  const { register, handleSubmit, reset, formState } = useForm({
    resolver: zodResolver(propertySchema),
    defaultValues: { property_type: "apartment", condition: "", listing_status: "draft", parking_spaces: 0 },
  });
  const errors = formState.errors;
  useEffect(() => {
    if (initial) reset(toFormValues(initial));
  }, [initial, reset]);

  const onSubmit = async (values) => {
    setError(null);
    try {
      const payload = toPayload(values, Boolean(propertyId));
      const saved = propertyId ? await api.properties.update(propertyId, payload) : await api.properties.create(payload);
      navigate(`/properties/${saved.id}`);
    } catch (caught) {
      setError(caught);
    }
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} noValidate className="space-y-6">
      <ErrorNote error={error} />
      <Card title="Basics">
        <div className="grid gap-4 sm:grid-cols-2">
          <TextField label="Title" registration={register("title")} error={errors.title?.message} />
          <SelectField label="Property type" registration={register("property_type")} options={PROPERTY_TYPES} />
          <SelectField
            label="Listing status"
            registration={register("listing_status")}
            hint="Listed properties appear publicly, without the street address."
            options={[
              { value: "draft", label: "Draft (private)" },
              { value: "listed", label: "Listed (public)" },
              ...(propertyId ? [{ value: "under_offer", label: "Under offer" }, { value: "sold", label: "Sold" }] : []),
            ]}
          />
          <SelectField label="Condition" registration={register("condition")} options={[{ value: "", label: "Not specified" }, ...CONDITIONS]} />
          <div className="sm:col-span-2">
            <TextAreaField label="Description" registration={register("description")} error={errors.description?.message} />
          </div>
        </div>
      </Card>
      <Card title="Location">
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <TextField label="Street address" hint="Kept private. It never appears in public listings or on the blockchain." registration={register("address_line1")} error={errors.address_line1?.message} />
          </div>
          <TextField label="Locality" registration={register("locality")} error={errors.locality?.message} hint="Links this property to its market data, if any is available." />
          <TextField label="City" registration={register("city")} error={errors.city?.message} />
          <TextField label="State" registration={register("state")} error={errors.state?.message} />
          <TextField label="Postal code" registration={register("postal_code")} error={errors.postal_code?.message} />
        </div>
      </Card>
      <Card title="Characteristics">
        <div className="grid gap-4 sm:grid-cols-3">
          <TextField label="Built-up area (sq ft)" type="number" step="0.01" registration={register("built_up_area_sqft")} error={errors.built_up_area_sqft?.message} hint="Required for an AI estimate." />
          <TextField label="Land area (sq ft)" type="number" step="0.01" registration={register("land_area_sqft")} error={errors.land_area_sqft?.message} />
          <TextField label="Construction year" type="number" registration={register("construction_year")} error={errors.construction_year?.message} />
          <TextField label="Bedrooms" type="number" registration={register("bedrooms")} error={errors.bedrooms?.message} />
          <TextField label="Bathrooms" type="number" registration={register("bathrooms")} error={errors.bathrooms?.message} />
          <TextField label="Parking spaces" type="number" registration={register("parking_spaces")} error={errors.parking_spaces?.message} />
          <TextField label="Floor number" type="number" registration={register("floor_number")} error={errors.floor_number?.message} />
          <TextField label="Total floors" type="number" registration={register("total_floors")} error={errors.total_floors?.message} />
          <TextField label="Amenities" placeholder="gym, pool, lift" hint="Separate with commas." registration={register("amenities")} error={errors.amenities?.message} />
        </div>
      </Card>
      <Card title="Prices">
        <div className="grid gap-4 sm:grid-cols-2">
          <TextField label="Asking price" type="number" step="0.01" hint="Needed to compare the price with the AI estimate and the locality." registration={register("asking_price")} error={errors.asking_price?.message} />
          <TextField label="Monthly rent" type="number" step="0.01" hint="Needed to work out the rental yield." registration={register("monthly_rent")} error={errors.monthly_rent?.message} />
          <TextField label="Last sale price" type="number" step="0.01" hint="Private." registration={register("last_sale_price")} error={errors.last_sale_price?.message} />
          <TextField label="Last sale date" type="date" registration={register("last_sale_date")} error={errors.last_sale_date?.message} />
        </div>
      </Card>
      <div className="flex justify-end gap-2">
        <Button variant="secondary" onClick={() => navigate(-1)}>
          Cancel
        </Button>
        <Button type="submit" busy={formState.isSubmitting}>
          {propertyId ? "Save changes" : "Register property"}
        </Button>
      </div>
    </form>
  );
}

export default function PropertyFormPage() {
  const { id } = useParams();
  const state = useAsync(() => (id ? api.properties.get(id) : Promise.resolve({ blank: true })), [id]);
  return (
    <>
      <PageHeader title={id ? "Edit property" : "Register a property"} subtitle={id ? "Changing the address or size resets a previous verification decision." : "You can add images and documents after saving."} />
      {!id && <PageGuide id="register" title="What happens when you register" steps={["Only the title and address are required. The more you add, the more the estimate and comparisons can use.", "A draft stays private. A listed property appears publicly, without its street address.", "After saving, you can add photos and documents, get an estimate, and create a digital twin."]} />}
      <Loadable state={state} label="Loading property">
        {(property) => <PropertyForm initial={property.blank ? null : property} propertyId={id} />}
      </Loadable>
    </>
  );
}
