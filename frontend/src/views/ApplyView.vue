<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api'

interface ChildEntry {
  firstName: string
  lastName: string
  heightInches: string
  age: string
  gender: string
  bikeColor1: string
  bikeColor2: string
  knowsHowToRide: string
  otherSiblings: string
  drawingFile: File | null
  drawingFileName: string
  dreamBikeDescription: string
}

function createChild(): ChildEntry {
  return {
    firstName: '',
    lastName: '',
    heightInches: '',
    age: '',
    gender: '',
    bikeColor1: '',
    bikeColor2: '',
    knowsHowToRide: '',
    otherSiblings: '',
    drawingFile: null,
    drawingFileName: '',
    dreamBikeDescription: '',
  }
}

const agency = reactive({
  agencyName: '',
  contactName: '',
  contactPhone: '',
  contactEmail: '',
})

const parent = reactive({
  firstName: '',
  lastName: '',
  address: '',
  city: '',
  zipCode: '',
  phone: '',
  email: '',
  primaryLanguage: '',
  englishSpeaker: '',
  preferredContact: '',
  transportationAccess: '',
})

const children = ref<ChildEntry[]>([createChild()])

const errors = reactive<Record<string, string>>({})
const submitting = ref(false)
const submitted = ref(false)
const referenceId = ref('')
const submitError = ref(false)
const showValidationSummary = ref(false)

const isDevMode = import.meta.env.VITE_AUTH_ENABLED === 'false' || !import.meta.env.VITE_AUTH_ENABLED

function fillTestData() {
  agency.agencyName = 'Salvation Army'
  agency.contactName = 'Maria Lopez'
  agency.contactPhone = '555-0101'
  agency.contactEmail = 'maria@salvationarmy.example'

  parent.firstName = 'Sarah'
  parent.lastName = 'Johnson'
  parent.address = '742 Evergreen Terrace'
  parent.city = 'Springfield'
  parent.zipCode = '62704'
  parent.phone = '555-1234'
  parent.email = 'sarah.johnson@example.com'
  parent.primaryLanguage = 'English'
  parent.englishSpeaker = 'yes'
  parent.preferredContact = 'email'
  parent.transportationAccess = 'yes'

  children.value = [
    {
      firstName: 'Emma',
      lastName: 'Johnson',
      heightInches: '48',
      age: '8',
      gender: 'Female',
      bikeColor1: 'Purple',
      bikeColor2: 'Pink',
      knowsHowToRide: 'yes',
      otherSiblings: 'yes',
      drawingFile: null,
      drawingFileName: '',
      dreamBikeDescription: 'A sparkly bike with streamers and a basket',
    },
    {
      firstName: 'Liam',
      lastName: 'Johnson',
      heightInches: '42',
      age: '6',
      gender: 'Male',
      bikeColor1: 'Red',
      bikeColor2: 'Blue',
      knowsHowToRide: 'no',
      otherSiblings: 'yes',
      drawingFile: null,
      drawingFileName: '',
      dreamBikeDescription: 'A fast bike with big wheels',
    },
  ]
}

function addChild() {
  children.value.push(createChild())
}

function removeChild(index: number) {
  if (children.value.length > 1) {
    children.value.splice(index, 1)
  }
}

function handleDrawingUpload(event: Event, index: number) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return

  const key = `child_${index}_drawing`
  delete errors[key]

  const validTypes = ['image/png', 'image/jpeg']
  if (!validTypes.includes(file.type)) {
    errors[key] = t('apply.drawingInvalidType')
    input.value = ''
    return
  }

  const maxSize = 5 * 1024 * 1024 // 5MB
  if (file.size > maxSize) {
    errors[key] = t('apply.drawingTooLarge')
    input.value = ''
    return
  }

  children.value[index].drawingFile = file
  children.value[index].drawingFileName = file.name
}

function clearErrors() {
  for (const key of Object.keys(errors)) {
    delete errors[key]
  }
}

function validate(): boolean {
  clearErrors()

  // Agency fields
  if (!agency.agencyName.trim()) errors['agency_agencyName'] = t('form.required')
  if (!agency.contactName.trim()) errors['agency_contactName'] = t('form.required')
  if (!agency.contactPhone.trim()) errors['agency_contactPhone'] = t('form.required')
  if (!agency.contactEmail.trim()) errors['agency_contactEmail'] = t('form.required')
  else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(agency.contactEmail.trim()))
    errors['agency_contactEmail'] = t('form.invalidEmail')

  // Parent fields
  if (!parent.firstName.trim()) errors['parent_firstName'] = t('form.required')
  if (!parent.lastName.trim()) errors['parent_lastName'] = t('form.required')
  if (!parent.address.trim()) errors['parent_address'] = t('form.required')
  if (!parent.city.trim()) errors['parent_city'] = t('form.required')
  if (!parent.zipCode.trim()) errors['parent_zipCode'] = t('form.required')
  if (!parent.phone.trim()) errors['parent_phone'] = t('form.required')
  if (!parent.email.trim()) errors['parent_email'] = t('form.required')
  else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(parent.email.trim()))
    errors['parent_email'] = t('form.invalidEmail')
  if (!parent.primaryLanguage.trim()) errors['parent_primaryLanguage'] = t('form.required')
  if (!parent.englishSpeaker) errors['parent_englishSpeaker'] = t('form.required')
  if (!parent.preferredContact) errors['parent_preferredContact'] = t('form.required')
  if (!parent.transportationAccess) errors['parent_transportationAccess'] = t('form.required')

  // Children fields
  children.value.forEach((child, i) => {
    if (!child.firstName.trim()) errors[`child_${i}_firstName`] = t('form.required')
    if (!child.lastName.trim()) errors[`child_${i}_lastName`] = t('form.required')
    if (!child.heightInches.trim()) {
      errors[`child_${i}_heightInches`] = t('apply.heightRequired')
    } else if (isNaN(Number(child.heightInches)) || Number(child.heightInches) <= 0) {
      errors[`child_${i}_heightInches`] = t('apply.heightNumeric')
    }
    if (!child.age.trim()) errors[`child_${i}_age`] = t('form.required')
    if (!child.gender) errors[`child_${i}_gender`] = t('form.required')
    if (!child.bikeColor1.trim()) errors[`child_${i}_bikeColor1`] = t('form.required')
    if (!child.bikeColor2.trim()) errors[`child_${i}_bikeColor2`] = t('form.required')
    if (!child.knowsHowToRide) errors[`child_${i}_knowsHowToRide`] = t('form.required')
  })

  return Object.keys(errors).length === 0
}

async function uploadDrawing(file: File): Promise<string | null> {
  try {
    const presignRes = await fetch(`${API_BASE}/uploads/presign`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        file_name: file.name,
        file_type: file.type,
        file_size: file.size,
        purpose: 'drawing',
      }),
    })

    if (!presignRes.ok) return null

    const data = await presignRes.json()
    const uploadUrl = data.upload_url
    const s3Key = data.s3_key

    const uploadRes = await fetch(uploadUrl, {
      method: 'PUT',
      headers: { 'Content-Type': file.type },
      body: file,
    })

    if (!uploadRes.ok) return null
    return s3Key
  } catch {
    return null
  }
}

async function handleSubmit() {
  showValidationSummary.value = false
  submitError.value = false

  if (!validate()) {
    showValidationSummary.value = true
    return
  }

  submitting.value = true

  try {
    // Upload drawings first
    const childrenData = await Promise.all(
      children.value.map(async (child) => {
        let drawingS3Key: string | null = null
        if (child.drawingFile) {
          drawingS3Key = await uploadDrawing(child.drawingFile)
        }

        return {
          first_name: child.firstName,
          last_name: child.lastName,
          height_inches: Number(child.heightInches),
          age: Number(child.age),
          gender: child.gender,
          bike_color_1: child.bikeColor1,
          bike_color_2: child.bikeColor2,
          knows_how_to_ride: child.knowsHowToRide === 'yes',
          other_siblings_enrolled: child.otherSiblings,
          drawing_image_s3_key: drawingS3Key || '',
          dream_bike_description: child.dreamBikeDescription,
        }
      })
    )

    const payload = {
      referring_agency: {
        agency_name: agency.agencyName,
        contact_name: agency.contactName,
        contact_phone: agency.contactPhone,
        contact_email: agency.contactEmail,
      },
      parent_guardian: {
        first_name: parent.firstName,
        last_name: parent.lastName,
        address: parent.address,
        city: parent.city,
        zip_code: parent.zipCode,
        phone: parent.phone,
        email: parent.email,
        primary_language: parent.primaryLanguage,
        english_speaker_in_household: parent.englishSpeaker === 'yes',
        preferred_contact_method: parent.preferredContact,
        transportation_access: parent.transportationAccess === 'yes',
      },
      children: childrenData,
    }

    const res = await fetch(`${API_BASE}/applications`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })

    if (!res.ok) {
      submitError.value = true
      return
    }

    const data = await res.json()
    referenceId.value = data.reference_number || data.application_id || data.referenceId || data.id || ''
    submitted.value = true
  } catch {
    submitError.value = true
  } finally {
    submitting.value = false
  }
}

function resetForm() {
  agency.agencyName = ''
  agency.contactName = ''
  agency.contactPhone = ''
  agency.contactEmail = ''
  parent.firstName = ''
  parent.lastName = ''
  parent.address = ''
  parent.city = ''
  parent.zipCode = ''
  parent.phone = ''
  parent.email = ''
  parent.primaryLanguage = ''
  parent.englishSpeaker = ''
  parent.preferredContact = ''
  parent.transportationAccess = ''
  children.value = [createChild()]
  clearErrors()
  submitted.value = false
  referenceId.value = ''
  submitError.value = false
  showValidationSummary.value = false
}
</script>

<template>
  <div class="apply-view">
    <!-- Confirmation Screen -->
    <div v-if="submitted" class="apply-confirmation">
      <h1>{{ t('apply.successTitle') }}</h1>
      <p>{{ t('apply.successMessage') }}</p>
      <div class="apply-confirmation__ref">
        <strong>{{ t('apply.referenceId') }}:</strong> {{ referenceId }}
      </div>
      <button type="button" class="btn btn--primary" @click="resetForm">
        {{ t('apply.submitAnother') }}
      </button>
    </div>

    <!-- Application Form -->
    <form v-else class="apply-form" novalidate @submit.prevent="handleSubmit">
      <h1>{{ t('apply.title') }}</h1>
      <p class="apply-form__intro">{{ t('apply.intro') }}</p>

      <button v-if="isDevMode" type="button" class="btn btn--dev" @click="fillTestData">
        🧪 Fill Test Data
      </button>

      <div v-if="showValidationSummary" class="apply-form__error-summary" role="alert">
        {{ t('apply.validationErrors') }}
      </div>

      <div v-if="submitError" class="apply-form__error-summary" role="alert">
        {{ t('apply.submitError') }}
      </div>

      <!-- Section 1: Referring Agency -->
      <fieldset class="apply-form__section">
        <legend>{{ t('apply.sectionAgency') }}</legend>

        <div class="form-group">
          <label for="agency-name">{{ t('apply.agencyName') }} *</label>
          <input id="agency-name" v-model="agency.agencyName" type="text" required
            :aria-invalid="!!errors['agency_agencyName']" />
          <span v-if="errors['agency_agencyName']" class="form-error" role="alert">{{ errors['agency_agencyName'] }}</span>
        </div>

        <div class="form-group">
          <label for="agency-contact-name">{{ t('apply.contactName') }} *</label>
          <input id="agency-contact-name" v-model="agency.contactName" type="text" required
            :aria-invalid="!!errors['agency_contactName']" />
          <span v-if="errors['agency_contactName']" class="form-error" role="alert">{{ errors['agency_contactName'] }}</span>
        </div>

        <div class="form-row">
          <div class="form-group">
            <label for="agency-contact-phone">{{ t('apply.contactPhone') }} *</label>
            <input id="agency-contact-phone" v-model="agency.contactPhone" type="tel" required
              :aria-invalid="!!errors['agency_contactPhone']" />
            <span v-if="errors['agency_contactPhone']" class="form-error" role="alert">{{ errors['agency_contactPhone'] }}</span>
          </div>

          <div class="form-group">
            <label for="agency-contact-email">{{ t('apply.contactEmail') }} *</label>
            <input id="agency-contact-email" v-model="agency.contactEmail" type="email" required
              :aria-invalid="!!errors['agency_contactEmail']" />
            <span v-if="errors['agency_contactEmail']" class="form-error" role="alert">{{ errors['agency_contactEmail'] }}</span>
          </div>
        </div>
      </fieldset>

      <!-- Section 2: Parent/Guardian -->
      <fieldset class="apply-form__section">
        <legend>{{ t('apply.sectionParent') }}</legend>

        <div class="form-row">
          <div class="form-group">
            <label for="parent-first-name">{{ t('apply.parentFirstName') }} *</label>
            <input id="parent-first-name" v-model="parent.firstName" type="text" required
              :aria-invalid="!!errors['parent_firstName']" />
            <span v-if="errors['parent_firstName']" class="form-error" role="alert">{{ errors['parent_firstName'] }}</span>
          </div>

          <div class="form-group">
            <label for="parent-last-name">{{ t('apply.parentLastName') }} *</label>
            <input id="parent-last-name" v-model="parent.lastName" type="text" required
              :aria-invalid="!!errors['parent_lastName']" />
            <span v-if="errors['parent_lastName']" class="form-error" role="alert">{{ errors['parent_lastName'] }}</span>
          </div>
        </div>

        <div class="form-group">
          <label for="parent-address">{{ t('apply.parentAddress') }} *</label>
          <input id="parent-address" v-model="parent.address" type="text" required
            :aria-invalid="!!errors['parent_address']" />
          <span v-if="errors['parent_address']" class="form-error" role="alert">{{ errors['parent_address'] }}</span>
        </div>

        <div class="form-row">
          <div class="form-group">
            <label for="parent-city">{{ t('apply.parentCity') }} *</label>
            <input id="parent-city" v-model="parent.city" type="text" required
              :aria-invalid="!!errors['parent_city']" />
            <span v-if="errors['parent_city']" class="form-error" role="alert">{{ errors['parent_city'] }}</span>
          </div>

          <div class="form-group">
            <label for="parent-zip">{{ t('apply.parentZip') }} *</label>
            <input id="parent-zip" v-model="parent.zipCode" type="text" required
              :aria-invalid="!!errors['parent_zipCode']" />
            <span v-if="errors['parent_zipCode']" class="form-error" role="alert">{{ errors['parent_zipCode'] }}</span>
          </div>
        </div>

        <div class="form-row">
          <div class="form-group">
            <label for="parent-phone">{{ t('apply.parentPhone') }} *</label>
            <input id="parent-phone" v-model="parent.phone" type="tel" required
              :aria-invalid="!!errors['parent_phone']" />
            <span v-if="errors['parent_phone']" class="form-error" role="alert">{{ errors['parent_phone'] }}</span>
          </div>

          <div class="form-group">
            <label for="parent-email">{{ t('apply.parentEmail') }} *</label>
            <input id="parent-email" v-model="parent.email" type="email" required
              :aria-invalid="!!errors['parent_email']" />
            <span v-if="errors['parent_email']" class="form-error" role="alert">{{ errors['parent_email'] }}</span>
          </div>
        </div>

        <div class="form-group">
          <label for="parent-language">{{ t('apply.primaryLanguage') }} *</label>
          <input id="parent-language" v-model="parent.primaryLanguage" type="text" required
            :aria-invalid="!!errors['parent_primaryLanguage']" />
          <span v-if="errors['parent_primaryLanguage']" class="form-error" role="alert">{{ errors['parent_primaryLanguage'] }}</span>
        </div>

        <div class="form-group">
          <label>{{ t('apply.englishSpeaker') }} *</label>
          <div class="radio-group" role="radiogroup" :aria-label="t('apply.englishSpeaker')">
            <label class="radio-label">
              <input v-model="parent.englishSpeaker" type="radio" name="englishSpeaker" value="yes" />
              {{ t('common.yes') }}
            </label>
            <label class="radio-label">
              <input v-model="parent.englishSpeaker" type="radio" name="englishSpeaker" value="no" />
              {{ t('common.no') }}
            </label>
          </div>
          <span v-if="errors['parent_englishSpeaker']" class="form-error" role="alert">{{ errors['parent_englishSpeaker'] }}</span>
        </div>

        <div class="form-group">
          <label for="parent-preferred-contact">{{ t('apply.preferredContact') }} *</label>
          <select id="parent-preferred-contact" v-model="parent.preferredContact" required
            :aria-invalid="!!errors['parent_preferredContact']">
            <option value="" disabled>{{ t('apply.selectOne') }}</option>
            <option value="WhatsApp">{{ t('apply.contactWhatsApp') }}</option>
            <option value="Phone Call">{{ t('apply.contactPhoneCall') }}</option>
            <option value="Text Message">{{ t('apply.contactTextMessage') }}</option>
            <option value="Email">{{ t('apply.contactEmail') }}</option>
          </select>
          <span v-if="errors['parent_preferredContact']" class="form-error" role="alert">{{ errors['parent_preferredContact'] }}</span>
        </div>

        <div class="form-group">
          <label>{{ t('apply.transportationAccess') }} *</label>
          <div class="radio-group" role="radiogroup" :aria-label="t('apply.transportationAccess')">
            <label class="radio-label">
              <input v-model="parent.transportationAccess" type="radio" name="transportationAccess" value="yes" />
              {{ t('common.yes') }}
            </label>
            <label class="radio-label">
              <input v-model="parent.transportationAccess" type="radio" name="transportationAccess" value="no" />
              {{ t('common.no') }}
            </label>
          </div>
          <span v-if="errors['parent_transportationAccess']" class="form-error" role="alert">{{ errors['parent_transportationAccess'] }}</span>
        </div>
      </fieldset>

      <!-- Section 3: Children (repeatable) -->
      <fieldset class="apply-form__section">
        <legend>{{ t('apply.sectionChildren') }}</legend>

        <p class="apply-form__training-wheels-note" role="note">
          {{ t('apply.trainingWheelsNote') }}
        </p>

        <div v-for="(child, index) in children" :key="index" class="child-entry">
          <div class="child-entry__header">
            <h3>{{ t('apply.child') }} {{ index + 1 }}</h3>
            <button v-if="children.length > 1" type="button" class="btn btn--danger btn--sm"
              @click="removeChild(index)" :aria-label="`${t('apply.removeChild')} ${index + 1}`">
              {{ t('apply.removeChild') }}
            </button>
          </div>

          <div class="form-row">
            <div class="form-group">
              <label :for="`child-${index}-first-name`">{{ t('apply.childFirstName') }} *</label>
              <input :id="`child-${index}-first-name`" v-model="child.firstName" type="text" required
                :aria-invalid="!!errors[`child_${index}_firstName`]" />
              <span v-if="errors[`child_${index}_firstName`]" class="form-error" role="alert">{{ errors[`child_${index}_firstName`] }}</span>
            </div>

            <div class="form-group">
              <label :for="`child-${index}-last-name`">{{ t('apply.childLastName') }} *</label>
              <input :id="`child-${index}-last-name`" v-model="child.lastName" type="text" required
                :aria-invalid="!!errors[`child_${index}_lastName`]" />
              <span v-if="errors[`child_${index}_lastName`]" class="form-error" role="alert">{{ errors[`child_${index}_lastName`] }}</span>
            </div>
          </div>

          <div class="form-row form-row--three">
            <div class="form-group">
              <label :for="`child-${index}-height`">{{ t('apply.childHeight') }} *</label>
              <input :id="`child-${index}-height`" v-model="child.heightInches" type="text" inputmode="numeric" required
                :aria-invalid="!!errors[`child_${index}_heightInches`]"
                :aria-describedby="`child-${index}-height-help`" />
              <small :id="`child-${index}-height-help`" class="form-help">{{ t('apply.childHeightHelp') }}</small>
              <span v-if="errors[`child_${index}_heightInches`]" class="form-error" role="alert">{{ errors[`child_${index}_heightInches`] }}</span>
            </div>

            <div class="form-group">
              <label :for="`child-${index}-age`">{{ t('apply.childAge') }} *</label>
              <input :id="`child-${index}-age`" v-model="child.age" type="text" inputmode="numeric" required
                :aria-invalid="!!errors[`child_${index}_age`]" />
              <span v-if="errors[`child_${index}_age`]" class="form-error" role="alert">{{ errors[`child_${index}_age`] }}</span>
            </div>

            <div class="form-group">
              <label :for="`child-${index}-gender`">{{ t('apply.childGender') }} *</label>
              <select :id="`child-${index}-gender`" v-model="child.gender" required
                :aria-invalid="!!errors[`child_${index}_gender`]">
                <option value="" disabled>{{ t('apply.selectGender') }}</option>
                <option value="Male">{{ t('apply.genderMale') }}</option>
                <option value="Female">{{ t('apply.genderFemale') }}</option>
                <option value="Non-binary">{{ t('apply.genderNonBinary') }}</option>
              </select>
              <span v-if="errors[`child_${index}_gender`]" class="form-error" role="alert">{{ errors[`child_${index}_gender`] }}</span>
            </div>
          </div>

          <div class="form-row">
            <div class="form-group">
              <label :for="`child-${index}-color1`">{{ t('apply.bikeColor1') }} *</label>
              <input :id="`child-${index}-color1`" v-model="child.bikeColor1" type="text" required
                :aria-invalid="!!errors[`child_${index}_bikeColor1`]" />
              <span v-if="errors[`child_${index}_bikeColor1`]" class="form-error" role="alert">{{ errors[`child_${index}_bikeColor1`] }}</span>
            </div>

            <div class="form-group">
              <label :for="`child-${index}-color2`">{{ t('apply.bikeColor2') }} *</label>
              <input :id="`child-${index}-color2`" v-model="child.bikeColor2" type="text" required
                :aria-invalid="!!errors[`child_${index}_bikeColor2`]" />
              <span v-if="errors[`child_${index}_bikeColor2`]" class="form-error" role="alert">{{ errors[`child_${index}_bikeColor2`] }}</span>
            </div>
          </div>

          <div class="form-group">
            <label>{{ t('apply.knowsHowToRide') }} *</label>
            <div class="radio-group" role="radiogroup" :aria-label="t('apply.knowsHowToRide')">
              <label class="radio-label">
                <input v-model="child.knowsHowToRide" type="radio" :name="`knowsHowToRide_${index}`" value="yes" />
                {{ t('common.yes') }}
              </label>
              <label class="radio-label">
                <input v-model="child.knowsHowToRide" type="radio" :name="`knowsHowToRide_${index}`" value="no" />
                {{ t('common.no') }}
              </label>
            </div>
            <span v-if="errors[`child_${index}_knowsHowToRide`]" class="form-error" role="alert">{{ errors[`child_${index}_knowsHowToRide`] }}</span>
          </div>

          <div class="form-group">
            <label :for="`child-${index}-siblings`">{{ t('apply.otherSiblings') }}</label>
            <input :id="`child-${index}-siblings`" v-model="child.otherSiblings" type="text" />
          </div>

          <!-- Dream Bike Drawing -->
          <div class="child-entry__drawing">
            <h4>{{ t('apply.sectionDrawing') }}</h4>

            <div class="form-group">
              <label :for="`child-${index}-drawing`">{{ t('apply.drawingUpload') }}</label>
              <small class="form-help">{{ t('apply.drawingUploadHelp') }}</small>
              <input :id="`child-${index}-drawing`" type="file" accept="image/png,image/jpeg"
                @change="handleDrawingUpload($event, index)" />
              <span v-if="child.drawingFileName" class="form-file-name">{{ child.drawingFileName }}</span>
              <span v-if="errors[`child_${index}_drawing`]" class="form-error" role="alert">{{ errors[`child_${index}_drawing`] }}</span>
            </div>

            <div class="form-group">
              <label :for="`child-${index}-dream-desc`">{{ t('apply.dreamBikeDescription') }}</label>
              <textarea :id="`child-${index}-dream-desc`" v-model="child.dreamBikeDescription" rows="3"
                :placeholder="t('apply.dreamBikePlaceholder')"></textarea>
            </div>
          </div>
        </div>

        <button type="button" class="btn btn--secondary" @click="addChild">
          + {{ t('apply.addChild') }}
        </button>
      </fieldset>

      <div class="apply-form__actions">
        <button type="submit" class="btn btn--primary" :disabled="submitting">
          {{ submitting ? t('apply.submitting') : t('apply.submitApplication') }}
        </button>
      </div>
    </form>
  </div>
</template>

<style scoped>
.apply-view {
  max-width: 720px;
  margin: 0 auto;
  padding: 1rem;
}

.apply-form__intro {
  color: #555;
  margin-bottom: 1.5rem;
}

.apply-form__section {
  border: 1px solid #ddd;
  border-radius: 8px;
  padding: 1.25rem;
  margin-bottom: 1.5rem;
}

.apply-form__section legend {
  font-size: 1.15rem;
  font-weight: 600;
  padding: 0 0.5rem;
  color: #333;
}

.apply-form__training-wheels-note {
  background: #fff8e1;
  border-left: 4px solid #f9a825;
  padding: 0.75rem 1rem;
  margin-bottom: 1rem;
  font-style: italic;
  font-size: 0.9rem;
}

.form-group {
  display: flex;
  flex-direction: column;
  margin-bottom: 1rem;
  flex: 1;
  min-width: 0;
}

.form-group label {
  font-weight: 500;
  margin-bottom: 0.25rem;
  font-size: 0.9rem;
}

.form-group input[type="text"],
.form-group input[type="email"],
.form-group input[type="tel"],
.form-group select,
.form-group textarea {
  padding: 0.5rem;
  border: 1px solid #ccc;
  border-radius: 4px;
  font-size: 1rem;
  width: 100%;
  box-sizing: border-box;
}

.form-group input[aria-invalid="true"],
.form-group select[aria-invalid="true"] {
  border-color: #d32f2f;
}

.form-group textarea {
  resize: vertical;
}

.form-group input[type="file"] {
  font-size: 0.9rem;
  margin-top: 0.25rem;
}

.form-help {
  color: #777;
  font-size: 0.8rem;
  margin-bottom: 0.25rem;
}

.form-error {
  color: #d32f2f;
  font-size: 0.8rem;
  margin-top: 0.25rem;
}

.form-file-name {
  color: #388e3c;
  font-size: 0.8rem;
  margin-top: 0.25rem;
}

.form-row {
  display: flex;
  gap: 1rem;
}

.form-row--three {
  flex-wrap: wrap;
}

.radio-group {
  display: flex;
  gap: 1.5rem;
  margin-top: 0.25rem;
}

.radio-label {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  font-weight: 400;
  cursor: pointer;
}

.radio-label input[type="radio"] {
  margin: 0;
}

.child-entry {
  border: 1px solid #e6ddd0;
  border-radius: 6px;
  padding: 1rem;
  margin-bottom: 1rem;
  background: #f5f0e8;
}

.child-entry__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.75rem;
}

.child-entry__header h3 {
  margin: 0;
  font-size: 1.05rem;
}

.child-entry__drawing {
  border-top: 1px solid #e6ddd0;
  padding-top: 0.75rem;
  margin-top: 0.5rem;
}

.child-entry__drawing h4 {
  margin: 0 0 0.75rem;
  font-size: 0.95rem;
  color: #555;
}

.btn {
  padding: 0.6rem 1.25rem;
  border: none;
  border-radius: 4px;
  font-size: 0.95rem;
  cursor: pointer;
  font-weight: 500;
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn--primary {
  background: #1976d2;
  color: #fff;
}

.btn--primary:hover:not(:disabled) {
  background: #1565c0;
}

.btn--secondary {
  background: #e6ddd0;
  color: #333;
}

.btn--secondary:hover {
  background: #d0d0d0;
}

.btn--danger {
  background: #d32f2f;
  color: #fff;
}

.btn--danger:hover {
  background: #c62828;
}

.btn--sm {
  padding: 0.3rem 0.75rem;
  font-size: 0.85rem;
}

.apply-form__actions {
  text-align: center;
  margin-top: 1rem;
  margin-bottom: 2rem;
}

.apply-form__error-summary {
  background: #ffebee;
  border: 1px solid #ef9a9a;
  border-radius: 4px;
  padding: 0.75rem 1rem;
  color: #c62828;
  margin-bottom: 1rem;
}

.apply-confirmation {
  text-align: center;
  padding: 2rem 1rem;
}

.apply-confirmation h1 {
  color: #388e3c;
}

.apply-confirmation__ref {
  background: #e8f5e9;
  border-radius: 6px;
  padding: 1rem;
  margin: 1.5rem 0;
  font-size: 1.1rem;
  word-break: break-all;
}

/* Responsive: 320px minimum */
@media (max-width: 600px) {
  .apply-view {
    padding: 0.5rem;
  }

  .apply-form__section {
    padding: 0.75rem;
  }

  .form-row {
    flex-direction: column;
    gap: 0;
  }

  .form-row--three {
    flex-direction: column;
  }

  .child-entry__header {
    flex-direction: column;
    align-items: flex-start;
    gap: 0.5rem;
  }
}
.btn--dev {
  background: #f39c12;
  color: #fff;
  border: none;
  padding: 6px 14px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.8rem;
  margin-bottom: 1rem;
}

.btn--dev:hover {
  background: #e67e22;
}
</style>
